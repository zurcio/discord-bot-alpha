# ====== EXPLORE COMMAND ==========
import random
import discord
from discord.ext import commands
from core.decorators import requires_profile, requires_oxygen
from core.utils import get_max_health, get_max_oxygen
from core.shared import load_json
from core.players import save_profile
from systems.combat import simulate_combat, choose_random_enemy
from core.constants import PLANETS_FILE
from core.cooldowns import check_and_set_cooldown
from core.guards import require_no_lock
from systems.ship_sys import derive_ship_effects
from core.rewards import apply_rewards 
from systems.crew_sys import maybe_spawn_crew
from core.quest_progress import update_quest_progress_for_enemy_kill
from collections import defaultdict
from core.items import load_items, get_item_by_id
# NEW
from core.skills_hooks import award_skill
from systems.raids import load_state, save_state, charge_battery


def _soldier_xp_for_explore(planet_id: int) -> int:
    """
    Soldier XP for Explore wins. Data-driven later; simple planet-scaled fallback for now.
    """
    return max(1, 25 * int(planet_id))

class Explore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="explore", aliases=["exp"])
    @requires_profile()
    @requires_oxygen(25)
    @require_no_lock()
    async def explore(self, ctx):
        """Explore uncharted sectors of space and fight elite enemies (1 hr cooldown)."""
        if not await check_and_set_cooldown(ctx, "explore", 3600):
            return

        player = ctx.player

        # Planet materials multiplier
        planet_id = str(player.get("current_planet", 1))
        planets_root = load_json(PLANETS_FILE) or {}
        planets_data = planets_root.get("planets") if isinstance(planets_root.get("planets"), dict) else planets_root
        planet_data = planets_data.get(planet_id, {}) if isinstance(planets_data, dict) else {}
        materials_mult = float(planet_data.get("materials_mult", 1))

        enemy_key, enemy = choose_random_enemy(player, category="elite")
        if not enemy:
            await ctx.send(f"{ctx.author.mention}, there are no elite enemies here.")
            return

        combat_result = simulate_combat(player, enemy, fight_type="explore")

        embed = discord.Embed(
            title=f"Exploration Encounter - {enemy['name']}",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Player: {player['username']} | Planet {planet_id}")

        if combat_result["player_won"]:
            player["health"] = combat_result["player_hp_left"]

            # Base rewards (let core.rewards stack multipliers)
            base_scrap = random.randint(50, 100)
            base_xp = random.randint(80, 150)

            res = apply_rewards(
                player,
                {"scrap": base_scrap, "xp": base_xp},
                ctx_meta={"command": "explore", "planet": planet_id},
                tags=["explore"]
            )

            # Drops handling (materials_mult + ship double_drops only for non-lootboxes)
            drops_text = "None"
            if combat_result["drops"]:
                inv = player.get("inventory", {}) or {}
                items_data = load_items()
                eff = derive_ship_effects(player)
                double_items = bool(eff.get("double_drops"))

                counts = defaultdict(int)
                for d in combat_result["drops"]:
                    counts[str(d)] += 1

                lootbox_table = (items_data or {}).get("lootboxes", {}) or {}
                supply_crate_table = (items_data or {}).get("supply_crates", {}) or {}
                drops_table = (items_data or {}).get("drops", {}) or {}
                pretty = []
                for iid, base_count in counts.items():
                    is_lootbox = iid in lootbox_table
                    is_supply_crate = iid in supply_crate_table
                    is_enemy_drop = iid in drops_table
                    qty = base_count
                    # Don't multiply lootboxes, supply crates, or enemy drops by planet mult
                    # Enemy drops only get ship double_drops bonus
                    if not is_lootbox and not is_supply_crate and not is_enemy_drop:
                        qty = int(max(1, round(qty * materials_mult)))
                    if double_items and not is_lootbox and not is_supply_crate:
                        qty *= 2

                    inv[iid] = int(inv.get(iid, 0)) + qty

                    meta = get_item_by_id(items_data, iid)
                    name = meta["name"] if meta and "name" in meta else str(iid)
                    pretty.append(f"{name} x{qty}")

                player["inventory"] = inv
                drops_text = ", ".join(pretty) if pretty else "None"

            # Soldier skill XP on win
            s_xp = _soldier_xp_for_explore(int(planet_id))
            new_lvl, ups = award_skill(ctx, "soldier", s_xp)

            embed.add_field(name="Outcome", value=f"✅ You defeated the {enemy['name']}! Consumed 25 Oxygen", inline=False)
            embed.add_field(name="HP Remaining", value=f"{player['health']} / {get_max_health(player)} ❤️", inline=True)
            embed.add_field(name="Oxygen Remaining", value=f"{player['oxygen']} / {get_max_oxygen(player)} 🫁", inline=True)
            embed.add_field(
                name="Rewards",
                value=f"{ctx.author.mention} earned 💰 {res['applied']['scrap']} Scrap + ⭐ {res['applied']['xp']} XP! • ⚔️ Soldier +{s_xp} XP" + (f" (L{new_lvl} +{ups})" if ups > 0 else ""),
                inline=False
            )
            embed.add_field(name="Dropped Items", value=drops_text, inline=False)

            # QUEST PROGRESSION - Defeat Y in Explore
            prev = (player.get("active_quest") or {}).get("progress", 0)
            completed = update_quest_progress_for_enemy_kill(player, str(enemy_key), source="explore")
            q = player.get("active_quest") or {}
            if q and not q.get("completed", False):
                newp = int(q.get("progress", 0))
                goal = int(q.get("goal", 0))
                if newp > prev:
                    await ctx.send(f"📜 Quest Progress: {newp} / {goal}")
            elif completed:
                await ctx.send("✅ Quest Complete!")

            save_profile(ctx.author.id, player)

        else:
            # Player lost
            player["health"] = 0
            old_level = player["level"]
            player["level"] = max(1, player["level"] - 1)
            player["xp"] = 0

            embed.add_field(name="Outcome", value=f"💀 {enemy['name']} defeated you! Consumed 25 Oxygen", inline=False)
            embed.add_field(name="Level Lost", value=f"Level {old_level} → Level {player['level']}", inline=False)
            embed.add_field(name="HP Remaining", value=f"{player['health']} / {get_max_health(player)} ❤️", inline=True)
            embed.add_field(name="Pro Tip", value="Recover your health at a Space Station with `!heal`. Use `!buy medkit` to purchase medkits!", inline=False)

        #raid battery charge
        state = load_state()
        charge_battery(state, str(ctx.author.id), "explore")  
        save_state(state)


        save_profile(ctx.author.id, player)
        await ctx.send(embed=embed)

        await maybe_spawn_crew(ctx, source="explore")

async def setup(bot):
    await bot.add_cog(Explore(bot))
