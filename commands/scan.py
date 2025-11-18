import random
import discord
from discord.ext import commands
from core.decorators import requires_profile, requires_oxygen
from core.shared import load_json
from core.players import save_profile
from core.utils import get_max_health, get_max_oxygen
from core.constants import PLANETS_FILE
from core.cooldowns import check_and_set_cooldown
from systems.combat import choose_random_enemy, simulate_combat 
from core.items import load_items, get_item_by_id, get_item_display_name
from core.guards import require_no_lock
from systems.ship_sys import derive_ship_effects
from core.rewards import apply_rewards
from collections import defaultdict  
from core.quest_progress import update_quest_progress_for_materials, update_quest_progress_for_enemy_kill
from systems.crew_sys import maybe_spawn_crew
# NEW
from core.skills_hooks import award_skill
from core.sector import ensure_sector, sector_bonus_multiplier
from systems.raids import load_state, save_state, charge_battery

def _soldier_xp_for_scan(planet_id: int) -> int:
    """
    Soldier XP for Scan wins. Data-driven later; simple planet-scaled fallback for now.
    """
    return max(1, 10 * int(planet_id))

class Scan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="scan", aliases=["sc"])
    @requires_profile()
    @require_no_lock()
    @requires_oxygen(5)
    async def scan(self, ctx):
        """Scan your current location for anomalies and encounter a random enemy."""
        if not await check_and_set_cooldown(ctx, "scan", 60):
            return

        player = ctx.player
        planet_id = str(player.get("current_planet", 1))

        # Load planets config; support both schemas:
        planets_root = load_json(PLANETS_FILE) or {}
        planets_data = planets_root.get("planets") if isinstance(planets_root.get("planets"), dict) else planets_root
        planet_data = planets_data.get(planet_id, {}) if isinstance(planets_data, dict) else {}
        materials_mult = float(planet_data.get("materials_mult", 1))  # apply to non-lootbox drops

        enemy_key, enemy = choose_random_enemy(player, category="basic")
        if not enemy:
            await ctx.send(f"{ctx.author.mention}, there are no enemies here.")
            return

        combat_result = simulate_combat(player, enemy, fight_type="scan")

        embed = discord.Embed(
            title=f"Scan Result - {enemy.get('name', enemy_key)}",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url="https://i.imgur.com/ZQZAc7h.png")
        embed.set_footer(text=f"Player: {player['username']} | Planet {planet_id}")

        # Update player health after combat
        player["health"] = combat_result["player_hp_left"]

        if combat_result["player_won"]:
            # Base rewards (let core.rewards apply multipliers: planet, ship, bank, etc.)
            base_scrap = random.randint(5, 25)
            base_xp = random.randint(10, 30)

            res = apply_rewards(
                player,
                {"scrap": base_scrap, "xp": base_xp},
                ctx_meta={"command": "scan", "planet": planet_id},
                tags=["scan"]
            )

            # Handle drops (planet materials_mult + ship double_drops only for non-lootboxes)
            drops_text = "None"
            if combat_result["drops"]:
                inv = player.get("inventory", {}) or {}
                items_data = load_items()
                eff = derive_ship_effects(player)
                double_items = bool(eff.get("double_drops"))

                counts = defaultdict(int)
                for d in combat_result["drops"]:
                    counts[str(d)] += 1

                pretty = []
                lootbox_table = (items_data or {}).get("lootboxes", {}) or {}
                supply_crate_table = (items_data or {}).get("supply_crates", {}) or {}
                drops_table = (items_data or {}).get("drops", {}) or {}
                for iid, base_count in counts.items():
                    is_lootbox = iid in lootbox_table
                    is_supply_crate = iid in supply_crate_table
                    is_enemy_drop = iid in drops_table
                    qty = base_count
                    # Don't multiply lootboxes, supply crates, or enemy drops by planet mult
                    # Enemy drops only get ship double_drops bonus
                    if not is_lootbox and not is_supply_crate and not is_enemy_drop:
                        qty = int(max(1, round(qty * materials_mult)))
                    if double_items:
                        qty *= 2

                    inv[iid] = int(inv.get(iid, 0)) + qty

                    # Only advance materials quests for non-lootboxes and non-supply-crates
                    if not is_lootbox and not is_supply_crate:
                        try:
                            update_quest_progress_for_materials(player, str(iid), int(qty))
                        except TypeError:
                            try:
                                update_quest_progress_for_materials(player, {str(iid): int(qty)})
                            except Exception:
                                pass

                    item = get_item_by_id(items_data, iid)
                    display = get_item_display_name(item, iid, self.bot)
                    pretty.append(f"{display} x{qty}")

                player["inventory"] = inv
                drops_text = ", ".join(pretty) if pretty else "None"

            # Soldier skill XP on win
            s_xp = _soldier_xp_for_scan(int(planet_id))
            new_lvl, ups = award_skill(ctx, "soldier", s_xp)

            embed.add_field(name="Outcome", value=f"✅ You defeated the {enemy.get('name', enemy_key)}! Consumed 5 Oxygen", inline=False)
            embed.add_field(name="Turns", value=f"{combat_result['rounds']}", inline=True)
            embed.add_field(name="Player HP Left", value=f"{combat_result['player_hp_left']}", inline=True)
            embed.add_field(
                name="Rewards",
                value=f"{ctx.author.mention} earned 💰 {res['applied']['scrap']} Scrap + ⭐ {res['applied']['xp']} XP! • ⚔️ Soldier +{s_xp} XP" + (f" (L{new_lvl} +{ups})" if ups > 0 else ""),
                inline=False
            )
            embed.add_field(name="Dropped Items", value=drops_text, inline=False)

            # QUEST PROGRESSION - Defeat X in Scan
            prev = (player.get("active_quest") or {}).get("progress", 0)
            completed = update_quest_progress_for_enemy_kill(player, str(enemy_key), source="scan")
            q = player.get("active_quest") or {}
            if q and not q.get("completed", False):
                newp = int(q.get("progress", 0))
                goal = int(q.get("goal", 0))
                if newp > prev:
                    await ctx.send(f"📜 Quest Progress: {newp} / {goal}")
            elif completed:
                await ctx.send("✅ Quest Complete!")

            save_profile(ctx.author.id, player)

        elif not combat_result["player_won"] and combat_result["enemy_hp_left"] > 0:
            old_level = player["level"]
            player["health"] = 0
            player["level"] = max(1, player["level"] - 1)
            player["xp"] = 0

            embed.add_field(name="Outcome", value=f"💀 {enemy.get('name', enemy_key)} defeated you! Consumed 5 Oxygen", inline=False)
            embed.add_field(name="Level Lost", value=f"Level {old_level} → Level {player['level']}", inline=False)
            embed.add_field(name="Turns", value=f"{combat_result['rounds']}", inline=True)
            embed.add_field(name="Enemy HP Left", value=f"{combat_result['enemy_hp_left']}", inline=True)
            embed.add_field(name="Pro Tip", value="Recover your health at a Space Station with `!heal`. Use `!buy medkit` to purchase medkits!", inline=False)

        else:
            embed.add_field(name="Outcome", value=f"🤝 Draw with {enemy.get('name', enemy_key)}.", inline=False)
            embed.add_field(name="Turns", value=f"{combat_result['rounds']}", inline=True)
            embed.add_field(name="Player HP Left", value=f"{combat_result['player_hp_left']}", inline=True)
            embed.add_field(name="Enemy HP Left", value=f"{combat_result['enemy_hp_left']}", inline=True)


        #raid battery charge
        state = load_state()
        charge_battery(state, str(ctx.author.id), "scan")  # or "work_scavenge"/"research"/"explore"
        save_state(state)

        save_profile(ctx.author.id, player)
        await ctx.send(embed=embed)

        # Attempt to spawn crew after scan
        await maybe_spawn_crew(ctx, source="scan")

async def setup(bot):
    await bot.add_cog(Scan(bot))