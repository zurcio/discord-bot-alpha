import discord
from discord.ext import commands
from core.decorators import requires_profile
from systems.dismantle_sys import dismantle_item
from core.guards import require_no_lock


class Dismantle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="dismantle", aliases=["dis"])
    @requires_profile()
    @require_no_lock()
    async def dismantle(self, ctx, *, args: str):
        """
        Dismantle higher-tier materials into lower-tier ones.
        Example: !dismantle plasteel sheet 3
        """
        parts = args.lower().split()
        if len(parts) < 1:
            await ctx.send("❌ Usage: `!dismantle <item name> [amount]`")
            return

        # Parse amount (default 1)
        try:
            amount = int(parts[-1])
            item_name = " ".join(parts[:-1])
            if not item_name:
                raise ValueError
        except ValueError:
            item_name = " ".join(parts)
            amount = 1

        player = ctx.player
        result = dismantle_item(player, item_name, amount)

        embed = discord.Embed(
            title="🧰 Dismantle",
            description=result,
            color=discord.Color.dark_gray()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Dismantle(bot))
