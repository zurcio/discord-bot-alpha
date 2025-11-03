import random, time, discord, asyncio, copy
from datetime import timedelta  # NEW
from discord.ext import commands
from core.decorators import requires_profile
from core.cooldowns import get_cooldown, set_cooldown 
from core.shared import load_json, save_json
from core.constants import ENEMIES_FILE, ITEMS_FILE, PLANETS_FILE
from core.players import save_profile
from core.utils import get_max_health, get_max_oxygen, add_xp  
from core.guards import require_no_lock
from core.items import get_item_by_id
from core.quest_progress import update_quest_progress_for_materials 
from core.rewards import apply_rewards 
from core.cooldowns import check_cooldown_only, command_cooldowns

QUEST_COOLDOWN = 10800          # 3 hours in seconds
SHORT_QUEST_COOLDOWN = 2700     # 45 minutes

class Quest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Helper: resolve item by name (case-insensitive) to (id, display_name)
    def _resolve_item_id_and_name(self, items_data: dict, wanted_name: str):
        wn = (wanted_name or "").strip().lower()
        if not isinstance(items_data, dict):
            return wn, wanted_name.capitalize()
        for cat, items in items_data.items():
            if not isinstance(items, dict):
                continue
            for iid, meta in items.items():
                nm = (meta.get("name") or "").strip().lower()
                if nm == wn:
                    return str(iid), meta.get("name", wanted_name.capitalize())
        return wn, wanted_name.capitalize()
    
    # NEW: estimate rewards with multipliers without mutating/saving the real player
    def _estimate_applied_rewards(self, player: dict, base: dict) -> dict:
        """
        Returns {'scrap': int, 'xp': int, 'items': {id: qty}} that would be applied
        by core.rewards.apply_rewards given 'base'. Uses a deep copy of player.
        """
        from core.rewards import apply_rewards  # local import to avoid cycles
        sim_player = copy.deepcopy(player or {})
        payload = copy.deepcopy(base or {})
        res = apply_rewards(sim_player, payload, ctx_meta={"source": "quest_preview"}, tags=["quest", "preview"])
        # Expect res.get("applied", {}) to hold final applied numbers
        applied = res.get("applied", {}) if isinstance(res, dict) else {}
        out = {
            "scrap": int(applied.get("scrap", 0) or 0),
            "xp": int(applied.get("xp", 0) or 0),
            "items": dict(applied.get("items", {}) or {})
        }
        return out

    # NEW: which material families are unlocked for this planet
    def _allowed_material_families(self, planet_id: int) -> set[str]:
        """
        Unlocks:
          P1–2: plasteel, circuit
          P3–4: + plasma
          P5+:  + biofiber
        """
        p = max(1, int(planet_id or 1))
        allowed = {"plasteel", "circuit"}
        if p >= 3:
            allowed.add("plasma")
        if p >= 5:
            allowed.add("biofiber")
        return allowed

    # NEW: classify a crafting key/output into a material family
    def _recipe_family(self, key: str) -> str:
        k = str(key).lower()
        if k.startswith("plasteel_") or k == "plasteel":
            return "plasteel"
        if k in {"microchip", "processor", "motherboard", "quantum_computer"}:
            return "circuit"
        if k.startswith("plasma_") or k == "plasma":
            return "plasma"
        if k.startswith("bio") or "bio_" in k or k in {"biopolymer", "bio_gel", "bio_metal_hybrid", "bio_material_block"}:
            return "biofiber"
        return "unknown"

    def _pick_planet_enemy(self, enemies: dict, planet_id: int, category: str | None = None) -> tuple[str | None, str | None]:
        """
        enemies.json is grouped by planet sections (e.g., 'P1E', 'P2E', ...).
        Pick a random enemy from the player's current planet section.
        If 'category' is provided, restrict to that category (e.g., 'basic' or 'elite').
        Returns (enemy_key, enemy_display_name) or (None, None) if no match in this planet.
        """
        if not isinstance(enemies, dict) or not enemies:
            return None, None

        pid = max(1, int(planet_id or 1))
        section = enemies.get(f"P{pid}E") or enemies.get(f"P{pid}")
        if not isinstance(section, dict):
            return None, None

        # Build pool filtered by category if provided
        pool = []
        for eid, meta in section.items():
            if not isinstance(meta, dict):
                continue
            if category and str(meta.get("category", "")).lower() != category.lower():
                continue
            pool.append((str(eid), str(meta.get("name") or eid)))

        if not pool:
            return None, None

        return random.choice(pool)


    def _choose_quest_type(self) -> str:
        """
        Weighted mix:
          - collect_materials: 22%
          - defeat_scan:       22%
          - defeat_explore:    18%
          - gamble_win:        10%
          - do_trade:          13%
          - craft_material:    15%
        """
        roll = random.random()
        if roll < 0.22: return "collect_materials"
        if roll < 0.44: return "defeat_scan"
        if roll < 0.62: return "defeat_explore"
        if roll < 0.72: return "gamble_win"
        if roll < 0.85: return "do_trade"
        return "craft_material"

    def _pick_craft_target(self, items_data: dict, planet_id: int) -> tuple[str, str, int]:
        """
        Choose a material recipe id and display name with bias toward tier-2 materials.
        Tiers (by crafting key):
          T2: plasteel_sheet, microchip, plasma_slag, biopolymer
          T3: plasteel_bar,   processor,  plasma_charge, bio_gel
          T4: plasteel_beam,  motherboard,plasma_core,   bio_metal_hybrid
          T5: plasteel_block, quantum_computer, plasma_module, bio_material_block
        Returns (recipe_key, display_name, tier_number).
        """
        t2 = ["plasteel_sheet", "microchip", "plasma_slag", "biopolymer"]
        t3 = ["plasteel_bar", "processor", "plasma_charge", "bio_gel"]
        t4 = ["plasteel_beam", "motherboard", "plasma_core", "bio_metal_hybrid"]
        t5 = ["plasteel_block", "quantum_computer", "plasma_module", "bio_material_block"]

        p = max(1, int(planet_id or 1))
        allowed_fams = self._allowed_material_families(p)

        # Build weighted pool biased to T2 and filtered by unlocked families
        pool: list[tuple[str, int]] = []
        def add(keys, tier, weight):
            for k in keys:
                if self._recipe_family(k) in allowed_fams:
                    pool.extend([(k, tier)] * weight)

        add(t2, 2, 6)  # strong bias
        if p >= 3: add(t3, 3, 3)
        if p >= 5: add(t4, 4, 2)
        if p >= 7: add(t5, 5, 1)

        # Fallback if pool empty (e.g., very early planet)
        if not pool:
            # Prefer the lowest unlocked family’s tier-2 if possible
            for k in t2:
                if self._recipe_family(k) in allowed_fams:
                    pool.append((k, 2))
            if not pool:
                pool.append((t2[0], 2))

        key, tier = random.choice(pool)
        name = key
        try:
            name = items_data.get("materials", {}).get(key, {}).get("name", key)
        except Exception:
            pass
        return key, name, tier


    def generate_random_quest(self, player: dict, enemies: dict, planet_id: int, items_data: dict) -> dict:
        """
        Generates one of:
          - collect_materials
          - defeat_scan (defeat X of Y in Scan)
          - defeat_explore (defeat Y in Explore)
          - gamble_win (win X Scrap from gambling)
          - craft_material
        """
        qtype = self._choose_quest_type()
        p = max(1, int(planet_id))

        if qtype == "collect_materials":
            # Restrict materials by unlock rules
            allowed_fams = self._allowed_material_families(p)
            fam_list = sorted(allowed_fams) or ["plasteel", "circuit"]
            mat_base = random.choice(fam_list)
            _, mat_name = self._resolve_item_id_and_name(items_data, mat_base)

            base = 6 + 3 * min(p, 10)  # 9..36
            goal = max(8, min(60, int(base + random.randint(-2, 4))))

            scrap = 200 * p + random.randint(25, 75) * p
            xp = 80 * p + random.randint(10, 30) * p

            lootbox_id = None
            lootbox_qty = 0
            if random.random() < 0.15:
                lootbox_id = ["300", "301", "302", "303", "304"][min((p - 1) // 2, 4)]
                lootbox_qty = 1

            desc = f"Collect {goal}x {mat_name}."
            return {
                "description": desc,
                "type": "work",
                "progress": 0,
                "goal": goal,
                "completed": False,
                "target_type": "material",
                "target_item_id": str(mat_base),
                "target_name": mat_name,
                "material_id": str(mat_base),
                "reward": {
                    "scrap": int(scrap),
                    "xp": int(xp),
                    **({"lootbox": str(lootbox_id), "lootbox_qty": int(lootbox_qty)} if lootbox_id else {})
                }
            }

        if qtype in ("defeat_scan", "defeat_explore"):
            # Enforce categories: Scan=basic, Explore=elite
            req_cat = "basic" if qtype == "defeat_scan" else "elite"
            enemy_id, enemy_name = self._pick_planet_enemy(enemies or {}, planet_id, category=req_cat)
            if not enemy_id:
                # No valid enemy for this planet/category; fall back to a materials quest
                return self.generate_random_quest(player, enemies, planet_id, items_data)

            # Goals (your current simplified values)
            if qtype == "defeat_scan":
                goal = random.randint(3, 5)
            else:
                goal = 1

            desc = f"Defeat {goal}x {enemy_name} in {'Scan' if qtype == 'defeat_scan' else 'Explore'}."
            scrap = 220 * p + random.randint(25, 75) * p
            xp = 85 * p + random.randint(10, 30) * p
            return {
                "description": desc,
                "type": qtype,
                "progress": 0,
                "goal": goal,
                "completed": False,
                "enemy_id": str(enemy_id),
                "enemy_name": enemy_name,
                "reward": {"scrap": int(scrap), "xp": int(xp)}
            }


        if qtype == "gamble_win":
            # Target scrap to win; scale with planet and sector
            sector = max(1, int(player.get("sector") or 1))
            target = 500 * p * max(1, sector // 2) + random.randint(0, 250 * p)
            desc = f"Win {target:,} Scrap through gambling."
            scrap = 180 * p + random.randint(25, 75) * p
            xp = 70 * p + random.randint(10, 30) * p
            return {
                "description": desc,
                "type": "gamble_win",
                "progress": 0,
                "goal": int(target),
                "completed": False,
                "reward": {"scrap": int(scrap), "xp": int(xp)},
            }
        
        if qtype == "do_trade":
            # Any one successful trade completes it
            desc = "Make a trade with the Space Merchant."
            p = max(1, int(planet_id))
            scrap = 180 * p + random.randint(15, 50) * p
            xp = 70 * p + random.randint(10, 25) * p
            return {
                "description": desc,
                "type": "do_trade",
                "progress": 0,
                "goal": 1,
                "completed": False,
                "reward": {"scrap": int(scrap), "xp": int(xp)}
            }

        if qtype == "craft_material":
            # Pick a craft target only from unlocked families
            recipe_key, display_name, tier = self._pick_craft_target(items_data or {}, planet_id)
            # Quantity scales down with higher tiers
            if tier == 2:
                goal = random.randint(3, 5)
            elif tier == 3:
                goal = random.randint(2, 4)
            elif tier == 4:
                goal = random.randint(1, 3)
            else:  # tier 5+
                goal = 1

            scrap = 200 * p + random.randint(25, 75) * p
            xp = 80 * p + random.randint(10, 30) * p
            desc = f"Craft {goal}x {display_name}."
            return {
                "description": desc,
                "type": "craft_material",
                "progress": 0,
                "goal": int(goal),
                "completed": False,
                "target_item_id": str(recipe_key),
                "recipe_id": str(recipe_key),
                "target_name": display_name,
                "reward": {"scrap": int(scrap), "xp": int(xp)}
            }

        # Fallback
        return self.generate_random_quest(player, enemies, planet_id, items_data)



    def format_reward(self, reward: dict, items_data: dict) -> str:
        parts = []
        if reward.get("scrap"):
            parts.append(f"{int(reward['scrap']):,} Scrap")
        if reward.get("xp"):
            parts.append(f"{int(reward['xp']):,} XP")
        if reward.get("lootbox") and reward.get("lootbox_qty", 0) > 0:
            lb_id = str(reward["lootbox"])
            qty = int(reward["lootbox_qty"])
            # Try to resolve lootbox name if present in items.json
            lb_name = "Lootbox"
            if isinstance(items_data, dict):
                for cat, items in items_data.items():
                    if isinstance(items, dict) and lb_id in items:
                        lb_name = items[lb_id].get("name", lb_name)
                        break
                # some schemas have items_data["lootboxes"]
                if "lootboxes" in items_data and isinstance(items_data["lootboxes"], dict):
                    lb_name = items_data["lootboxes"].get(lb_id, {}).get("name", lb_name)
            parts.append(f"{qty}x {lb_name}")
        return ", ".join(parts) if parts else "None"
        
    @commands.command(name="quest", aliases=["q"])
    @requires_profile()
    @require_no_lock()
    async def quest(self, ctx, action: str | None = None):
        """Accept, check progress, claim, or cancel a random quest."""
        player = ctx.player
        now = int(time.time())

        # Load files
        enemies = load_json(ENEMIES_FILE)
        items = load_json(ITEMS_FILE)
        planet_id = player.get("max_unlocked_planet", 1)
        quest = player.get("active_quest", None)

        # Handle subcommand: cancel
        if action and action.lower() in ("cancel", "c"):
            if not quest:
                await ctx.send(f"{ctx.author.mention}, you don’t have an active quest.")
                return
            player["active_quest"] = None
            save_profile(ctx.author.id, player)
            await ctx.send("🗑️ Your active quest has been canceled.")
            return

        # Handle claiming rewards if quest is completed
        if quest and quest.get("completed", False):
            reward = quest.get("reward", {})
            scrap_reward = int(reward.get("scrap", 0) or 0)
            xp_reward = int(reward.get("xp", 0) or 0)
            lootbox_id = reward.get("lootbox")
            lootbox_qty = int(reward.get("lootbox_qty", 0) or 0)

            base = {"scrap": scrap_reward, "xp": xp_reward}
            if lootbox_id and lootbox_qty > 0:
                base["items"] = {str(lootbox_id): lootbox_qty}

            # Track level before applying rewards
            prev_level = int(player.get("level", 1) or 1)

            # Apply multipliers and persist result to player
            res = apply_rewards(player, base, ctx_meta={"source": "quest"}, tags=["quest"])

            # Clear active quest and save
            player["active_quest"] = None
            save_profile(ctx.author.id, player)

            applied = res.get("applied", {})
            lines = [
                f"💰 Scrap: **{int(applied.get('scrap', 0)):,}**",
                f"⭐ XP: **{int(applied.get('xp', 0)):,}**",
            ]
            if lootbox_id and lootbox_qty > 0:
                items = load_json(ITEMS_FILE) or {}
                lb_name = items.get("lootboxes", {}).get(str(lootbox_id), {}).get("name", "Lootbox")
                lines.append(f"🎁 Lootbox: **{lootbox_qty}x {lb_name}**")

            # Level-up announcement
            new_level = int(player.get("level", prev_level) or prev_level)
            if new_level > prev_level:
                try:
                    max_hp = get_max_health(player)
                    max_o2 = get_max_oxygen(player)
                    lines.append(f"⬆️ Level Up! Now Level **{new_level}** (HP {max_hp}, O₂ {max_o2})")
                except Exception:
                    lines.append(f"⬆️ Level Up! Now Level **{new_level}**")

            embed = discord.Embed(
                title="🎉 Quest Complete!",
                description="You claimed your quest rewards!\n\n" + "\n".join(lines),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            return


        # If quest in progress, show status
        if quest and not quest.get("completed", False):
            embed = discord.Embed(
                title=f"📜 Active Quest: {quest['description']}",
                description=f"Progress: **{quest['progress']} / {quest['goal']}**",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Type !quest cancel to cancel this quest.")
            await ctx.send(embed=embed)
            return

        # No active quest — use check-only cooldown helper (does not set)
        ok = await check_cooldown_only(ctx, "quest")
        if not ok:
            return

        # Generate a candidate quest and prompt for acceptance
        candidate = self.generate_random_quest(player, enemies, planet_id, items)

        # Build a base reward payload to estimate multipliers
        base_preview = {
            "scrap": int(candidate.get("reward", {}).get("scrap", 0) or 0),
            "xp": int(candidate.get("reward", {}).get("xp", 0) or 0),
        }
        lb_id_preview = candidate.get("reward", {}).get("lootbox")
        lb_qty_preview = int(candidate.get("reward", {}).get("lootbox_qty", 0) or 0)
        if lb_id_preview and lb_qty_preview > 0:
            base_preview["items"] = {str(lb_id_preview): lb_qty_preview}

        # Estimate applied rewards with multipliers for display
        est = self._estimate_applied_rewards(player, base_preview)
        est_scrap = int(est.get("scrap", 0))
        est_xp = int(est.get("xp", 0))
        # Resolve lootbox name if present
        lb_name_preview = None
        if lb_id_preview and lb_qty_preview > 0:
            lb_name_preview = "Lootbox"
            if isinstance(items, dict):
                if "lootboxes" in items and isinstance(items["lootboxes"], dict):
                    lb_name_preview = items["lootboxes"].get(str(lb_id_preview), {}).get("name", lb_name_preview)
                else:
                    # fallback scan of categories
                    for cat, table in items.items():
                        if isinstance(table, dict) and str(lb_id_preview) in table:
                            lb_name_preview = table[str(lb_id_preview)].get("name", lb_name_preview)
                            break

        reward_preview_str = f"{est_scrap:,} Scrap, {est_xp:,} XP"
        if lb_name_preview:
            reward_preview_str += f", {lb_qty_preview}x {lb_name_preview}"

        preview = discord.Embed(
            title="🧭 New Quest Available",
            description=candidate["description"],
            color=discord.Color.purple()
        )
        preview.add_field(name="Goal", value=f"{candidate['goal']} total", inline=True)
        preview.add_field(name="Reward (with bonuses)", value=reward_preview_str, inline=True)  # CHANGED
        preview.set_footer(text=f"Type 'yes' to accept or 'no' to decline (15s).")
        await ctx.send(f"{ctx.author.mention}", embed=preview)

        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.content.lower() in ("yes", "no")

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=15)
            answer = msg.content.lower()
        except asyncio.TimeoutError:
            answer = "no"

        if answer == "yes":
            # Accept quest: set active and apply full cooldown
            player["active_quest"] = candidate
            set_cooldown(ctx.author.id, "quest", now + command_cooldowns["quest"], ctx.author.name)
            save_profile(ctx.author.id, player)

            # Show the same reward preview with bonuses in the acceptance embed
            embed = discord.Embed(
                title="✅ Quest Accepted!",
                description= candidate["description"],
                color=discord.Color.green()
            )
            embed.add_field(name="Goal", value=f"{candidate['goal']} total", inline=True)
            embed.add_field(name="Reward (with bonuses)", value=reward_preview_str, inline=True)  # CHANGED
            await ctx.send(embed=embed)
        else:
            # Decline: shorter cooldown, no quest assigned
            set_cooldown(ctx.author.id, "quest", now + SHORT_QUEST_COOLDOWN, ctx.author.name)
            await ctx.send("❎ Quest declined. You can request a new one in 45 minutes.")

async def setup(bot):
    await bot.add_cog(Quest(bot))