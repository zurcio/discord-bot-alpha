import random
import asyncio
from core.utils import get_max_health
from core.shared import load_json, save_json
from core.players import calculate_combat_stats
from systems.ship_sys import derive_ship_effects
from core.constants import BOSSES_FILE, ITEMS_FILE, PLANETS_FILE
from systems.ship_sys import derive_ship_effects
from core.rewards import apply_rewards 
from typing import Tuple
from core.skills_hooks import award_player_skill


KEYCARD_IDS = {"400"}

def _keycard_count(player: dict) -> int:
    inv = (player or {}).get("inventory", {}) or {}
    total = 0
    for kid in KEYCARD_IDS:
        total += int(inv.get(str(kid), 0) or 0)
    return total


def load_boss_for_planet(planet_id: int, num_players: int):
    bosses = load_json(BOSSES_FILE) or {}
    planets = load_json(PLANETS_FILE) or {}
    pdata = planets.get(str(int(planet_id)), {}) or {}

    boss_id = pdata.get("boss_id")
    if not boss_id or boss_id not in bosses:
        # Fallbacks
        fallback_map = {
            1: "crawler_king",
            2: "crawler_queen",
            3: "don_slimeyoni",
            4: "the_sluggitive",
            5: "shrubbery",
            6: "audrey_iii",
            7: "rock_solid",
            8: "eternal_crystalloid",
            9: "the_battery",
            10: "deep_thought"
        }
        boss_id = fallback_map.get(int(planet_id)) or (next(iter(bosses.keys()), None))
        if not boss_id:
            raise ValueError(f"No boss configured for planet {planet_id} and bosses.json is empty.")

    boss = dict(bosses[boss_id])  # copy
    base_hp = int(boss.get("hp", 1) or 1)
    extra_players = max(0, int(num_players) - 1)
    boss["hp"] = base_hp + extra_players * int(base_hp * 0.75)
    boss.setdefault("name", boss_id)
    return boss

async def ensure_party_on_same_boss_planet(ctx, profiles: dict) -> int | None:
    """
    Ensure all players share the same max_unlocked_planet and are on that planet.
    Returns that planet_id if valid, else None (and sends a message).
    """
    # Gather values
    names = {pid: p.get("username", f"user_{pid}") for pid, p in profiles.items()}

    def to_int(v, default=1):
        try:
            return int(v if v is not None else default)
        except Exception:
            return default

    max_planets = {pid: to_int(p.get("max_unlocked_planet", p.get("current_planet", 1)), 1) for pid, p in profiles.items()}
    current_planets = {pid: to_int(p.get("current_planet", 1), 1) for pid, p in profiles.items()}

    unique_max = set(max_planets.values())
    if len(unique_max) != 1:
        # Group by max
        parts = []
        for pid, m in max_planets.items():
            parts.append(f"{names[pid]}: P{m}")
        await ctx.send("❌ All players must have the same max unlocked planet to attempt the boss.\n" +
                       " • " + "\n • ".join(parts))
        return None

    target = next(iter(unique_max))
    not_on_target = [names[pid] for pid, cur in current_planets.items() if cur != target]
    if not_on_target:
        await ctx.send(f"❌ All players must be on Planet {target} (current_planet == max_unlocked_planet).\n"
                       f"Move to Planet {target}:\n" +
                       " • " + "\n • ".join(not_on_target))
        return None

    return target

def _norm_id(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, dict):
        vid = val.get("id") or val.get("item_id")
        return str(vid) if vid is not None else None
    try:
        return str(val)
    except Exception:
        return None

def _get_equipped_ids(profile: dict) -> Tuple[str | None, str | None]:
    """
    Try multiple shapes:
      profile['equipment']['weapon'/'armor'] -> id or {id:..}
      profile['equipped']['weapon'/'armor']
      profile['equipped_weapon_id'] / ['equipped_armor_id']
      profile['weapon'] / ['armor'] -> id or {id:..}
      profile['weapon_id'] / ['armor_id']
    Returns (weapon_id_str_or_None, armor_id_str_or_None)
    """
    eq = profile.get("equipment") or {}
    if isinstance(eq, dict):
        w = _norm_id(eq.get("weapon"))
        a = _norm_id(eq.get("armor"))
        if w or a:
            return w, a

    eq2 = profile.get("equipped") or {}
    if isinstance(eq2, dict):
        w = _norm_id(eq2.get("weapon"))
        a = _norm_id(eq2.get("armor"))
        if w or a:
            return w, a

    w = _norm_id(profile.get("equipped_weapon_id") or profile.get("weapon") or profile.get("weapon_id"))
    a = _norm_id(profile.get("equipped_armor_id") or profile.get("armor") or profile.get("armor_id"))
    return w, a

def _resolve_item_name(items: dict, kind: str, iid: str | None) -> str:
    if not iid:
        return "None"
    try:
        entry = (items.get(kind, {}) or {}).get(str(iid), {})
        return entry.get("name") or str(iid)
    except Exception:
        return str(iid)

async def check_requirements(ctx, profiles: dict, boss: dict):
    req_weapon = boss.get("required_weapon_id")
    req_armor = boss.get("required_armor_id")
    # Normalize as strings for comparison
    req_weapon_id = _norm_id(req_weapon)
    req_armor_id = _norm_id(req_armor)

    items = load_json(ITEMS_FILE) or {}

    # Keycard requirement (ship mk6+ can override)
    missing_keycard = []
    for pid, p in profiles.items():
        eff = derive_ship_effects(p)
        if eff.get("keycard_override"):
            continue
        if _keycard_count(p) < 1:
            missing_keycard.append(p.get("username") or pid)
    if missing_keycard:
        await ctx.send("❌ " + ", ".join(missing_keycard) + " is missing the required keycard.")
        return False

    # Gear requirements (no ship override)
    if not req_weapon_id and not req_armor_id:
        return True  # no gear required

    gear_issues = []
    for pid, p in profiles.items():
        w_eq, a_eq = _get_equipped_ids(p)
        w_ok = (req_weapon_id is None) or (w_eq >= req_weapon_id)
        a_ok = (req_armor_id is None) or (a_eq >= req_armor_id)
        if not (w_ok and a_ok):
            uname = p.get("username", f"user_{pid}")
            want_w = _resolve_item_name(items, "weapons", req_weapon_id) if req_weapon_id else None
            want_a = _resolve_item_name(items, "armor", req_armor_id) if req_armor_id else None
            have_w = _resolve_item_name(items, "weapons", w_eq)
            have_a = _resolve_item_name(items, "armor", a_eq)
            parts = []
            if req_weapon_id and not w_ok:
                parts.append(f"You have the {have_w} weapon equipped, but you need the {want_w} (or better)")
            if req_armor_id and not a_ok:
                parts.append(f"You have the {have_a} armor equipped, but you need the {want_a} (or better)")
            gear_issues.append(f"{uname} — " + " | ".join(parts))

    if gear_issues:
        await ctx.send("❌ Gear requirements not met:\n• " + "\n• ".join(gear_issues))
        return False

    return True

async def confirm_participation(ctx, player_ids, boss_name, bot):
    mention_list = ", ".join([f"<@{pid}>" for pid in player_ids])
    await ctx.send(f"⚔️ {mention_list}, are you ready to challenge **{boss_name}**? Type `yes` or `no`.")
    ready_responses = {}
    def check_ready(m):
        return str(m.author.id) in player_ids and m.content.lower() in ["yes", "no"]
    while len(ready_responses) < len(player_ids):
        try:
            msg = await bot.wait_for("message", check=check_ready, timeout=30)
            ready_responses[str(msg.author.id)] = msg.content.lower()
        except asyncio.TimeoutError:
            await ctx.send("⌛ Bossfight cancelled due to timeout.")
            return False
    if not all(r == "yes" for r in ready_responses.values()):
        await ctx.send("❌ Not all players confirmed. Bossfight cancelled.")
        return False
    return True

def consume_keycard(player: dict) -> dict:
    """Consume one keycard unless ship overrides."""
    eff = derive_ship_effects(player)
    if eff.get("keycard_override"):
        return player
    inv = player.get("inventory", {}) or {}
    for kid in list(KEYCARD_IDS):
        key = str(kid)
        if int(inv.get(key, 0) or 0) > 0:
            inv[key] = int(inv.get(key, 0)) - 1
            if inv[key] <= 0:
                inv.pop(key, None)
            break
    player["inventory"] = inv
    return player

def compute_base_victory_rewards(boss: dict, planet_id: int, num_players: int) -> dict:
    """
    Determine base boss rewards before multipliers. Uses boss['rewards'] if present.
    Scales modestly with party size.
    Returns dict: { 'scrap': int, 'xp': int, 'items': {item_id: qty} }
    """
    rewards_cfg = (boss or {}).get("rewards", {}) or {}
    # Party scaling: +25% per extra player
    party_mult = 1.0 + 0.25 * max(0, num_players - 1)

    # Defaults if not configured in bosses.json
    base_scrap = int(rewards_cfg.get("scrap_base", 400 * int(planet_id)) * party_mult)
    base_xp = int(rewards_cfg.get("xp_base", 250 * int(planet_id)) * party_mult)

    items = {}
    # Optional single supply crate id in config
    lb = rewards_cfg.get("supply_crate_id")
    if lb:
        items[str(lb)] = 1

    return {"scrap": base_scrap, "xp": base_xp, "items": items}

# NEW: Soldier skill XP for bossfights (configurable via bosses.json)
def _soldier_xp_for_boss(planet_id: int, boss: dict) -> int:
    """
    Determine Soldier skill XP for a boss victory.
    Prefer boss['rewards']['soldier_xp']; fallback to 200 * planet_id.
    """
    try:
        rewards_cfg = (boss or {}).get("rewards", {}) or {}
        if "soldier_xp" in rewards_cfg:
            return max(0, int(rewards_cfg.get("soldier_xp") or 0))
    except Exception:
        pass
    return max(0, int(200 * int(planet_id)))

def grant_boss_victory_rewards(user_id: str, profile: dict, planet_id: int, boss: dict, num_players: int) -> dict:
    """
    Apply boss victory rewards through the central engine and grant Soldier skill XP.
    Returns dict with apply_rewards result and soldier award info:
      {
        "applied": {...},
        "soldier": {"xp": int, "level": int, "levels_gained": int}
      }
    """
    base = compute_base_victory_rewards(boss, planet_id, num_players)
    res = apply_rewards(
        profile,
        base,
        ctx_meta={"command": "bossfight", "planet": str(planet_id), "boss": boss.get("name")},
        tags=["bossfight"]
    )

    # Soldier skill XP
    sxp = _soldier_xp_for_boss(planet_id, boss)
    new_level, levels_gained = award_player_skill(profile, "soldier", sxp)

    res_out = dict(res)
    res_out["soldier"] = {"xp": int(sxp), "level": int(new_level), "levels_gained": int(levels_gained)}
    return res_out


## Helper function to calculate combat stats
async def run_combat(ctx, profiles: dict, player_ids: list, boss: dict, bot) -> bool:
    """
    Main combat loop. Uses a local `combatants` dict so saved profiles are untouched
    during combat. Returns True if boss defeated, False if players all die.
    """
    # Build combatants from profiles (do not mutate profiles yet)
    combatants = {}
    for pid in player_ids:
        profile = profiles[pid]
        stats = calculate_combat_stats(profile)
        combatants[pid] = {
            "profile_ref": profile,
            "attack": stats["attack"],
            "defense": stats["defense"],
            "health": profile.get("health", get_max_health(profile)),
            "username": profile.get("username", f"user_{pid}"),
            "defending": False,
            "dodging": False,
        }

    # Boss local stats (work on copies)
    boss_hp = int(boss.get("hp", 0))
    boss_base_attack = boss.get("attack", 0)
    boss_base_defense = boss.get("defense", 0)

    # Apply boss scaling multipliers if present (attack/defense multipliers per extra player)
    num_players = len(player_ids)
    scaling = boss.get("scaling", {}) or {}
    if num_players > 1 and scaling:
        atk_mult = float(scaling.get("attack_mult_per_player", 1.0)) ** (num_players - 1)
        def_mult = float(scaling.get("defense_mult_per_player", 1.0)) ** (num_players - 1)
        boss_attack = max(1, int(boss_base_attack * atk_mult))
        boss_defense = max(0, int(boss_base_defense * def_mult))
    else:
        boss_attack = int(boss_base_attack)
        boss_defense = int(boss_base_defense)

    # Precompute ability list (if none, fallback to single generic attack)
    abilities = list(boss.get("abilities", {}).values()) or [{
        "name": "Strike",
        "hit_chance": 0.85,
        "damage_mult": 1.0,
        "defense_pen": 0.0
    }]

    turn = 0
    alive_pids = [pid for pid in player_ids if combatants[pid]["health"] > 0]

    await ctx.send(f"🔥 The fight against **{boss['name']}** begins! HP: {boss_hp}")

    while boss_hp > 0 and alive_pids:
        pid = alive_pids[turn % len(alive_pids)]
        fighter = combatants[pid]

        # Skip if somehow dead
        if fighter["health"] <= 0:
            turn += 1
            alive_pids = [p for p in alive_pids if combatants[p]["health"] > 0]
            continue

        # Ask player for action
        await ctx.send(f"🎮 <@{pid}>, choose: `attack`, `defend`, `dodge`, or `power`.")

        def check_action(m):
            return str(m.author.id) == pid and m.content.lower() in ["attack", "defend", "dodge", "power"]

        try:
            msg = await bot.wait_for("message", check=check_action, timeout=30)
            action = msg.content.lower()
        except asyncio.TimeoutError:
            action = "attack"

        # Resolve player action -> damage to boss
        dmg_to_boss = 0
        if action == "attack":
            if random.random() < 0.8:
                dmg_to_boss = max(1, fighter["attack"] - boss_defense)
        elif action == "defend":
            fighter["defending"] = True  # always apply defending
            if random.random() < 0.5:    # optional counter-hit while defending
                dmg_to_boss = max(1, (fighter["attack"] // 2) - boss_defense)
        elif action == "dodge":
            fighter["dodging"] = True    # always apply dodging
            if random.random() < 0.3:    # optional poke while dodging
                dmg_to_boss = max(1, (fighter["attack"] // 3) - boss_defense)
        elif action == "power":
            if random.random() < 0.4:
                dmg_to_boss = max(5, fighter["attack"] * 2 - boss_defense)
        else:
            pass

        boss_hp -= dmg_to_boss
        boss_hp = max(0, boss_hp)  # keep non-negative
        if dmg_to_boss > 0:
            await ctx.send(f"💥 {fighter['username']} dealt **{dmg_to_boss}** damage! (Boss HP: {boss_hp})")
        else:
            await ctx.send(f"❌ {fighter['username']}'s move missed!")

        if boss_hp <= 0:
            break

        # Boss chooses ability and attacks the same player
        # Weighted ability choice
        if len(abilities) >= 3:
            # Assume order: [basic, medium, strong]
            ability = random.choices(
                population=abilities,
                weights=[60, 30, 10],
                k=1
            )[0]
        else:
            # Fallback: equal weighting if fewer abilities
            ability = random.choice(abilities)
        hit_chance = float(ability.get("hit_chance", 0.8))
        # reduce hit chance if player dodging
        if fighter.get("dodging"):
            hit_chance -= 0.4
        hit_roll = random.random()

        if hit_roll < hit_chance:
            dmg_mult = float(ability.get("damage_mult", 1.0))
            # effective defense after defense penetration
            def_pen = float(ability.get("defense_pen", 0.0))
            effective_def = int(fighter["defense"] * (1.0 - def_pen))
            raw = int(boss_attack * dmg_mult) - effective_def
            dmg_taken = max(1, raw)

            # defending halves the incoming damage
            if fighter.get("defending"):
                dmg_taken = dmg_taken // 2

            fighter["health"] -= dmg_taken
            await ctx.send(
                f"⚡ {boss['name']} used **{ability.get('name','attack')}** and hit {fighter['username']} "
                f"for **{dmg_taken}** damage! (HP: {fighter['health']})"
            )
        else:
            await ctx.send(f"🌀 {boss['name']} tried **{ability.get('name','attack')}** but missed {fighter['username']}!")

        # Remove dead players from rotation
        if fighter["health"] <= 0:
            await ctx.send(f"💀 {fighter['username']} has been defeated!")
            alive_pids = [p for p in alive_pids if combatants[p]["health"] > 0]

        # Reset temporary flags for this player
        fighter["defending"] = False
        fighter["dodging"] = False

        turn += 1

    # Persist combatant health back to in-memory profiles
    for pid, c in combatants.items():
        profile = profiles[pid]
        profile["health"] = max(0, int(c["health"]))
        profiles[pid] = profile

    return boss_hp <= 0

## Helper function to grant boss rewards (unlock planet + warpdrive)
def grant_boss_rewards(user_id: str, planet_id: int, profile: dict):
    next_planet = planet_id + 1
    # Unlock and move the player to the next planet
    profile["max_unlocked_planet"] = max(profile.get("max_unlocked_planet", 1), next_planet)
    profile["current_planet"] = next_planet  # NEW: auto-place on the unlocked planet

    items = load_json(ITEMS_FILE)
    warpdrives = items.get("warpdrives", {})

    inv = profile.get("inventory", {})

    # Remove old warpdrives
    for wid in list(inv.keys()):
        if wid in warpdrives:
            inv.pop(wid, None)

    new_warp_id = None
    for wid, wdata in warpdrives.items():
        if wdata.get("target_planet") == next_planet:
            inv[wid] = 1
            new_warp_id = wid
            break

    profile["inventory"] = inv
    print(f"[DEBUG] grant_boss_rewards -> {user_id}: {profile}")
    return new_warp_id, warpdrives.get(new_warp_id, {}).get("name")

