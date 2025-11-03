import random
from core.shared import load_json
from core.players import save_profile
from core.constants import PLANETS_FILE
from core.decorators import requires_profile
from core.cooldowns import check_and_set_cooldown
from discord.ext import commands
from core.cooldowns import command_cooldowns
from core.rewards import apply_rewards 
from core.sector import ensure_sector, sector_bonus_multiplier
from core.quest_progress import update_quest_progress_for_materials
from systems.crew_sys import maybe_spawn_crew
# NEW
from core.skills_hooks import worker_effects, award_skill
from systems.raids import load_state, save_state, charge_battery

WORK_COOLDOWN = 180  # 3 minutes in seconds

WORK_MATERIALS = {
    "scavenge": {
        "drops": [
            {"material": "plasteel",        "rarity": "common",   "chance": 0.7999, "min": 2, "max": 5},
            {"material": "plasteel_sheet",  "rarity": "uncommon", "chance": 0.15, "min": 1, "max": 2},
            {"material": "plasteel_bar",    "rarity": "rare",     "chance": 0.049, "min": 1, "max": 1},
            {"material": "plasteel_beam",   "rarity": "mythic",   "chance": 0.001, "min": 1, "max": 1},
            {"material": "plasteel_block",  "rarity": "legendary","chance": 0.0001, "min": 1, "max": 1},
        ]
    },
    "hack": {
        "drops": [
            {"material": "circuit",    "rarity": "common",   "chance": 0.7999, "min": 2, "max": 5},
            {"material": "microchip",  "rarity": "uncommon", "chance": 0.15, "min": 1, "max": 2},
            {"material": "processor",  "rarity": "rare",     "chance": 0.049, "min": 1, "max": 1},
            {"material": "motherboard","rarity": "mythic",   "chance": 0.001, "min": 1, "max": 1},
            {"material": "quantum_computer","rarity": "legendary","chance": 0.0001, "min": 1, "max": 1},
        ]
    },
    "extract": {
        "drops": [
            {"material": "plasma",         "rarity": "common",   "chance": 0.7999, "min": 2, "max": 5},
            {"material": "plasma_slag",    "rarity": "uncommon", "chance": 0.15, "min": 1, "max": 2},
            {"material": "plasma_charge",  "rarity": "rare",     "chance": 0.049, "min": 1, "max": 1},
            {"material": "plasma_core",    "rarity": "mythic",   "chance": 0.001, "min": 1, "max": 1},
            {"material": "plasma_module",  "rarity": "legendary","chance": 0.0001, "min": 1, "max": 1},
        ]
    },
    "harvest": {
        "drops": [
            {"material": "biofiber",   "rarity": "common",   "chance": 0.7999, "min": 2, "max": 5},
            {"material": "biopolymer", "rarity": "uncommon", "chance": 0.15, "min": 1, "max": 2},
            {"material": "bio_gel",    "rarity": "rare",     "chance": 0.049, "min": 1, "max": 1},
            {"material": "bio-metal_hybrid", "rarity": "mythic",   "chance": 0.001, "min": 1, "max": 1},
            {"material": "bio-material_block", "rarity": "legendary","chance": 0.0001, "min": 1, "max": 1},
        ]
    }
}

RARITY_MESSAGES = {
    "common": "",
    "uncommon": "✨ Wow! You found something uncommon!",
    "rare": "🌟 Awesome!! That's a rare find!",
    "mythic": "💎 MYTHICAL PULL!!!!! You struck gold!",
    "legendary": "🏆 LEGENDARY WORK!!!!!!!! The universe trembles at your luck!"
}

# NEW: Worker XP table by planet and command
_WORKER_XP_TABLE = {
    "scavenge": [4, 5, 8, 8, 8, 12, 12, 16, 16, 16],
    "hack":     [4, 5, 9, 9, 9, 13, 13, 18, 18, 18],
    "extract":  [4, 5, 8, 8, 8, 12, 12, 17, 17, 17],  # P1–P2 only if Overcharged
    "harvest":  [4, 5, 8, 8, 8, 12, 12, 17, 17, 17],  # P1–P4 only if Overcharged
}

def _worker_xp_for(cmd: str, planet: int, overcharged: bool) -> int:
    arr = _WORKER_XP_TABLE.get(cmd, _WORKER_XP_TABLE["scavenge"])
    p = max(1, min(10, int(planet)))
    # Respect planet gating for early planets unless Overcharged
    if cmd == "extract" and p < 3 and not overcharged:
        return 0
    if cmd == "harvest" and p < 5 and not overcharged:
        return 0
    return int(arr[p - 1])

def choose_material(drops, rarity_bias):
    adjusted = []
    total = 0
    for drop in drops:
        bias = rarity_bias.get(drop["rarity"], 1.0)
        adj_chance = drop["chance"] * bias
        adjusted.append((drop, adj_chance))
        total += adj_chance

    roll = random.random()
    cumulative = 0
    for drop, adj_chance in adjusted:
        cumulative += adj_chance / total
        if roll <= cumulative:
            qty = random.randint(drop["min"], drop["max"])
            return drop["material"], qty

    fallback = adjusted[0][0]
    return fallback["material"], random.randint(fallback["min"], fallback["max"])

def _update_quest_for_gain(player: dict, item_key: str, qty: int):  # NEW
    try:
        update_quest_progress_for_materials(player, str(item_key), int(qty))
    except TypeError:
        try:
            update_quest_progress_for_materials(player, {str(item_key): int(qty)})
        except Exception:
            pass


async def handle_work(ctx, command_name: str):
    player = ctx.player

    # ✅ Shared cooldown for all work commands
    if not await check_and_set_cooldown(ctx, "work", command_cooldowns["work"]):
        return

    # Load planet data robustly (supports both flat and { "planets": { ... } } shapes)
    planets_root = load_json(PLANETS_FILE) or {}
    planets_data = planets_root.get("planets") if isinstance(planets_root.get("planets"), dict) else planets_root

    # Use current planet if set; fallback to max_unlocked_planet
    planet_key = str(player.get("current_planet") or player.get("max_unlocked_planet", 1))
    planet_data = planets_data.get(planet_key) or {"scrap_mult": 1.0, "xp_mult": 1.0, "materials_mult": 1.0}
    p10_data = planets_data.get("10") or {"scrap_mult": 1.0, "xp_mult": 1.0, "materials_mult": 1.0}

    # Skills: Worker perks
    weff = worker_effects(player)
    overcharged = bool(weff.get("overcharged", False))
    tier_mult = float(weff.get("work_tier_weight_mult", 1.0))
    cross_chance = float(weff.get("cross_material_chance", 0.0))

    # Overcharged: use Planet 10 multipliers/bias
    src_planet = p10_data if overcharged else planet_data

    # Rarity bias: planet bias scaled by Worker tier multiplier for higher tiers
    rarity_bias = dict(src_planet.get("rarity_bias", {"common": 1.0, "uncommon": 1.0, "rare": 1.0, "mythic": 1.0, "legendary": 1.0}))
    for r in ("uncommon", "rare", "mythic", "legendary"):
        rarity_bias[r] = float(rarity_bias.get(r, 1.0)) * tier_mult

    # Pick material from drop table
    drop_info = WORK_MATERIALS[command_name]["drops"]
    material, qty = choose_material(drop_info, rarity_bias)
    # Find rarity for the material
    rarity = next((d["rarity"] for d in drop_info if d["material"] == material), "common")
    flair = RARITY_MESSAGES.get(rarity, "")

    # Apply planet scaling to materials only (keep base XP/Scrap unscaled — engine applies multipliers)
    qty = max(1, int(qty * float(src_planet.get("materials_mult", 1.0))))

    # Apply sector yield bonus to Work items (NOT to enemy drops)
    s = ensure_sector(player)
    qty = max(1, int(round(qty * sector_bonus_multiplier(s))))

    # Snapshot quest progress BEFORE inventory change (only for material-collection quests)
    q = player.get("active_quest") or {}
    track = str(q.get("type", "")).lower() in {"work", "collect_materials"}
    prev_prog = int(q.get("progress", 0)) if track else None

    # Add gathered material to inventory
    inv = player.get("inventory", {}) or {}
    inv[material] = int(inv.get(material, 0)) + qty
    player["inventory"] = inv

    # Update quest progress using the gained material key
    update_quest_progress_for_materials(player, material, qty)

    # Emit quest progress/complete message if it advanced
    if track:
        q2 = player.get("active_quest") or {}
        new_prog = int(q2.get("progress", 0))
        if prev_prog is not None and new_prog > prev_prog:
            goal = int(q2.get("goal", 0))
            tname = q2.get("target_name") or q2.get("material_name") or material
            if q2.get("completed"):
                await ctx.send(f"🪓 Quest Complete! You collected enough **{tname}**.")
            else:
                await ctx.send(f"🪓 Quest Progress: {new_prog} / {goal} {tname}.")

    # NEW: Post-100 cross-material bonus (Overcharged only)
    bonus_line = ""
    cross_map = {
        "scavenge": "circuit",
        "hack": "plasma",
        "extract": "biofiber",
        "harvest": "plasteel",
    }
    if overcharged and cross_chance > 0.0:
        if random.random() < min(0.75, max(0.0, cross_chance)):
            cm = cross_map.get(command_name)
            if cm:
                inv = player.get("inventory", {}) or {}
                inv[cm] = int(inv.get(cm, 0)) + 1
                player["inventory"] = inv
                _update_quest_for_gain(player, cm, 1)
                bonus_line = f"\n🔁 Worker bonus: You also found 1x {cm}!"

    # Base rewards (do NOT pre-apply planet/ship/bank multipliers here)
    base_scrap = random.randint(5, 10)
    base_xp = random.randint(5, 15)

    # Apply rewards via central engine (stacks planet/ship/bank, etc.)
    res = apply_rewards(
        player,
        {"scrap": base_scrap, "xp": base_xp},
        ctx_meta={"command": command_name, "planet": planet_key},
        tags=["work", command_name]
    )

    # NEW: Worker skill XP award
    w_xp = _worker_xp_for(command_name, int(planet_key), overcharged)
    lvl, ups = award_skill(ctx, "worker", w_xp)

   # Build XP note separately to avoid f-string backslash-in-expression
    xp_note = ""
    if w_xp > 0:
        xp_note = f"\n🛠️ Worker +{w_xp} XP" + (f" (L{lvl} +{ups})" if ups > 0 else "")
    xp_note = xp_note.strip()

    await ctx.send(
         f"{ctx.author.mention} performed **{command_name}** and gathered "
         f"{qty}x {material}! 💰 {res['applied']['scrap']} Scrap | ⭐ {res['applied']['xp']} XP. "
        f"Consumed 10 Oxygen.\n{flair}"
        f"{bonus_line}"
        f"{xp_note}"
     )

    state = load_state()
    charge_battery(state, str(ctx.author.id), f"work_{command_name}")  
    save_state(state)

    save_profile(ctx.author.id, player)

    await maybe_spawn_crew(ctx, source="work")