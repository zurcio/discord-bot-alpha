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

class Weekly(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="weekly")
    @requires_profile()
    @require_no_lock()
    async def weekly(self, ctx):
        """Claim a weekly reward of Scrap, XP, and items (7 day cooldown)."""
        from core.cooldowns import check_and_set_cooldown
        if not await check_and_set_cooldown(ctx, "weekly", 604800):
            return

        player = ctx.player
        planet_id = str(player.get("current_planet", 1))

        # Base rewards (progression only). Multipliers are applied by core.rewards providers.
        scrap_base = int(random.randint(100, 200) * max(1, player.get("max_unlocked_planet", 1)) * max(1, player.get("level", 1)))
        xp_base = int(random.randint(100, 200) * max(1, player.get("max_unlocked_planet", 1)))

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

        # Items scaled by progression (as before)
        med_kits_earned = 25 * max(1, ctx.player.get("max_unlocked_planet", 1))
        oxy_earned = 10 * max(1, ctx.player.get("max_unlocked_planet", 1))

        # Determine lootbox tier by planet
        planet = max(1, ctx.player.get("max_unlocked_planet", 1))
        if planet <= 2:
            lootbox_id = "300"  # Common
        elif planet <= 4:
            lootbox_id = "301"  # Uncommon
        elif planet <= 6:
            lootbox_id = "302"  # Rare
        elif planet <= 8:
            lootbox_id = "303"  # Mythic
        else:
            lootbox_id = "304"  # Legendary

        # Compose items to grant via rewards engine
        items_to_grant = {lootbox_id: 1}
        if medkit_id:
            items_to_grant[medkit_id] = items_to_grant.get(medkit_id, 0) + med_kits_earned
        if oxy_id:
            items_to_grant[oxy_id] = items_to_grant.get(oxy_id, 0) + oxy_earned

        # Credits (not part of rewards engine)
        credits = 1
        player["Credits"] = int(player.get("Credits", 0)) + credits

        # Apply XP/Scrap/Items centrally
        res = apply_rewards(
            player,
            {"scrap": scrap_base, "xp": xp_base, "items": items_to_grant},
            ctx_meta={"command": "weekly", "planet": planet_id},
            tags=["weekly"]
        )

        lootboxes = (items_data or {}).get("lootboxes", {})
        lootbox_name = lootboxes.get(lootbox_id, {}).get("name", "Lootbox")

        # Build message
        msg = f"{ctx.author.mention} claimed their weekly reward!\n"
        msg += f"💰 +{res['applied']['scrap']} Scrap\n"
        msg += f"⭐ +{res['applied']['xp']} XP"
        if res.get("xp_result", {}).get("leveled_up"):
            levels_gained = res["xp_result"].get("levels_gained", 1)
            msg += f"\n🎉 Level up! Now Level {player['level']} (+{levels_gained})."
        msg += f"\n🎁 +1 {lootbox_name}"
        msg += f"\n💳 +{credits} Credits"
        msg += f"\n🩹 +{med_kits_earned} Med Kits" if medkit_id else ""
        msg += f"\n🫧 +{oxy_earned} Oxygen Tanks" if oxy_id else ""
        msg += f"\n\nCome back in 7 days for your next weekly reward!"

        save_profile(ctx.author.id, player)
        await ctx.send(msg)

async def setup(bot):
    await bot.add_cog(Weekly(bot))
