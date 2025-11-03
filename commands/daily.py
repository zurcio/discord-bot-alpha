# ====== DAILY COMMAND ==========
import random
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.shared import load_json
from core.players import save_profile
from core.constants import ITEMS_FILE
from core.items import iterate_all_items
from core.guards import require_no_lock
from core.rewards import apply_rewards  # CHANGED

class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="daily")
    @requires_profile()
    @require_no_lock()
    async def daily(self, ctx):
        """Claim a daily reward of Scrap, XP, and items (24 hr cooldown)."""
        # keep the same cooldown name/length
        from core.cooldowns import check_and_set_cooldown
        if not await check_and_set_cooldown(ctx, "daily", 86400):
            return

        player = ctx.player
        planet_id = str(player.get("current_planet", 1))

        # Base rewards (progression only). Multipliers are applied by core.rewards providers.
        scrap_base = int(random.randint(10, 25) * max(1, player.get("max_unlocked_planet", 1)) * max(1, player.get("level", 1)))
        xp_base = int(random.randint(10, 25) * max(1, player.get("max_unlocked_planet", 1)))

        # --- look up item IDs for medkits and oxy tanks ---
        items_data = load_json(ITEMS_FILE)
        medkit_id = None
        oxy_id = None
        for iid, item in iterate_all_items(items_data):
            nm = item.get("name", "").lower()
            if nm == "medkit":
                medkit_id = str(iid)
            elif nm == "oxygen tank":
                oxy_id = str(iid)

        # Scale items by planet progression (same as before)
        med_kits_earned = 5 * max(1, player.get("max_unlocked_planet", 1))
        oxy_earned = 5 * max(1, player.get("max_unlocked_planet", 1))

        items_to_grant = {}
        if medkit_id:
            items_to_grant[medkit_id] = med_kits_earned
        if oxy_id:
            items_to_grant[oxy_id] = oxy_earned

        # Apply rewards centrally
        res = apply_rewards(
            player,
            {"scrap": scrap_base, "xp": xp_base, "items": items_to_grant},
            ctx_meta={"command": "daily", "planet": planet_id},
            tags=["daily"]
        )

        # Build message
        msg = f"{ctx.author.mention} claimed their daily reward!\n"
        msg += f"💰 +{res['applied']['scrap']} Scrap\n"
        msg += f"⭐ +{res['applied']['xp']} XP"
        if res.get("xp_result", {}).get("leveled_up"):
            levels_gained = res["xp_result"].get("levels_gained", 1)
            msg += f"\n🎉 Level up! Now Level {player['level']} (+{levels_gained})."

        if medkit_id:
            msg += f"\n🩹 +{med_kits_earned} Med Kits"
        if oxy_id:
            msg += f"\n🫧 +{oxy_earned} Oxygen Tanks"

        save_profile(ctx.author.id, player)
        await ctx.send(msg)

async def setup(bot):
    await bot.add_cog(Daily(bot))
