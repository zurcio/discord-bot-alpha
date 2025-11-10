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

        # Separate item name and amount string
        if len(parts) > 1:
            # Check if last part could be an amount
            potential_amount = parts[-1].lower()
            if potential_amount in ['all', 'half', 'max'] or potential_amount[-1:] in ['k', 'm', 'b'] or potential_amount.replace('.', '').isdigit():
                item_name = " ".join(parts[:-1])
                amount_str = potential_amount
            else:
                item_name = " ".join(parts)
                amount_str = None
        else:
            item_name = " ".join(parts)
            amount_str = None

        player = ctx.player
        result = dismantle_item(player, item_name, amount_str)

        embed = discord.Embed(
            title="🧰 Dismantle",
            description=result,
            color=discord.Color.dark_gray()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Dismantle(bot))
