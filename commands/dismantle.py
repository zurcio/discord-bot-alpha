import discord
from discord.ext import commands
from core.decorators import requires_profile
from systems.dismantle_sys import dismantle_item
from core.guards import require_no_lock
from core.parsing import parse_amount


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
        Supports: !dismantle psheet 5k, !dismantle pbar all, !dismantle pbeam half
        """
        parts = args.split()
        if len(parts) < 1:
            await ctx.send("❌ Usage: `!dismantle <item name> [amount]`")
            return

        # Try parsing last part as amount (supports k/m/b, all, half, numbers)
        parsed_amount = parse_amount(parts[-1]) if len(parts) > 1 else None
        
        if parsed_amount is not None:
            item_name = " ".join(parts[:-1])
            amount = parsed_amount
        else:
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
