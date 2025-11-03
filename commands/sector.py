import asyncio
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.players import save_profile
from core.utils import get_max_health, get_max_oxygen
from core.sector import ensure_sector, set_sector, format_sector_bonuses

# Persist these Credit Shop items across sector travel
PERSISTENT_ITEM_IDS = {"ship_token"}  # add more if future credit shop items should persist
FTL_ITEM_IDS = {"ftl_drive", "FTL Drive"}  # support id or name string

def _has_ftl_drive(player: dict) -> bool:
    inv = (player.get("inventory") or {})
    # accept either explicit id or item name as a key, depending on your items schema
    for k in list(FTL_ITEM_IDS) + list(inv.keys()):
        if str(k).lower() in { "ftl_drive", "ftl drive", "ftl-drive", "511" } and int(inv.get(k, 0) or 0) > 0:
            return True
    return False

def _consume_ftl_drive(player: dict) -> None:
    inv = (player.get("inventory") or {})
    for key in list(inv.keys()):
        if str(key).lower() in { "ftl_drive", "ftl drive", "ftl-drive", "511" }:
            cur = int(inv.get(key, 0) or 0)
            if cur > 0:
                inv[key] = cur - 1
                if inv[key] <= 0:
                    inv.pop(key, None)
                break
    player["inventory"] = inv

class Sector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sector")
    @requires_profile()
    async def sector(self, ctx, action: str | None = None):
        """
        View sector bonuses and optionally travel to the next sector if eligible.
        Usage:
          !sector            -> shows current sector and bonuses
          !sector travel     -> prompts to travel (requires FTL Drive and P10 cleared)
        """
        player = ctx.player
        sector = ensure_sector(player)
        max_planet = int(player.get("max_unlocked_planet", 1))

        # Show info
        if not action or action.lower() not in {"travel", "go", "advance"}:
            embed = discord.Embed(title="🛰️ Sector Overview", color=discord.Color.blurple())
            desc = format_sector_bonuses(sector)
            eligible = (max_planet >= 10)
            reqs = []
            if not eligible:
                reqs.append("• Beat Planet 10 to unlock Sector Travel.")
            if not _has_ftl_drive(player):
                reqs.append("• Requires an FTL Drive to travel.")
            if not reqs:
                reqs_line = "Ready to travel. Use `!sector travel`."
            else:
                reqs_line = "Requirements:\n" + "\n".join(reqs)
            embed.description = f"{desc}\n\n{reqs_line}"
            await ctx.send(embed=embed)
            return

        # Travel flow
        if max_planet < 10:
            await ctx.send("🚫 You must defeat the Planet 10 boss before sector travel is unlocked.")
            return
        if not _has_ftl_drive(player):
            await ctx.send("🚫 You need an FTL Drive in your inventory to travel.")
            return

        warn = (
            "⚠️ Sector Travel Warning\n"
            "• All inventory items will be removed (Credit Shop items persist).\n"
            "• Equipped gear will be unequipped and cleared.\n"
            "• All Scrap not in your Bank will be lost.\n"
            "• Your level resets to 1 (XP reset).\n"
            "• You restart at Planet 1.\n"
            "• Your Bank balance, Ship, and Credits are preserved.\n"
            "• You will gain permanent sector bonuses to XP, enemy drop chance, work item yield, and global probabilities.\n\n"
            "Type 'yes' to confirm within 20 seconds, or 'no' to cancel."
        )
        await ctx.send(warn)

        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.content.lower().strip() in {"yes", "no"}

        try:
            msg = await self.bot.wait_for("message", timeout=20.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("⏳ Sector travel canceled (timeout).")
            return

        if msg.content.lower().strip() != "yes":
            await ctx.send("❎ Sector travel canceled.")
            return

        # Consume FTL Drive
        _consume_ftl_drive(player)

        # Preserve Credit Shop items (e.g., Ship Token)
        inv_old = (player.get("inventory") or {})
        inv_preserved = {}
        for iid in PERSISTENT_ITEM_IDS:
            qty = int(inv_old.get(iid, 0) or 0)
            if qty > 0:
                inv_preserved[iid] = qty

        # Reset per spec (preserve Bank, Ship, Credits; wipe enhancements)
        player["inventory"] = inv_preserved
        player["equipped"] = {"weapon": None, "armor": None}
        player["enhancements"] = {}  # remove all gear enhancements
        player["Scrap"] = 0
        player["xp"] = 0
        player["level"] = 1
        player["current_planet"] = 1
        player["max_unlocked_planet"] = 1

        # Restore vitals
        player["health"] = get_max_health(player)
        player["oxygen"] = get_max_oxygen(player)

        # Advance sector
        set_sector(player, sector + 1)

        save_profile(ctx.author.id, player)

        new_desc = format_sector_bonuses(player["sector"])
        embed = discord.Embed(
            title="🚀 Sector Travel Complete",
            description=f"You are now in Sector {player['sector']}.\n\n{new_desc}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Sector(bot))