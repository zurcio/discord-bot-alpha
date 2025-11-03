import discord
from discord.ext import commands
from core.players import load_profile, save_profile
from core.utils import get_max_health, get_max_oxygen


class Start(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="start", aliases=["begin", "register"])
    async def start(self, ctx):
        """Register a new player profile."""
        uid = str(ctx.author.id)
        if load_profile(uid):
            await ctx.send(f"{ctx.author.mention}, you’re already registered. Try `tutorial`,`scan`, `work`, `research`, or `explore`.")
            return

        # Create baseline profile
        profile = {
            "id": uid,
            "username": ctx.author.name,
            "level": 1,
            "xp": 0,
            "total_xp": 0,
            "Scrap": 0,
            "current_planet": 1,
            "max_unlocked_planet": 1,
            "default_planet": 1,
            "equipped": {"weapon": None, "armor": None},
            "inventory": {},
        }
        # Initialize vitals using current equipment (none → base caps)
        profile["health"] = get_max_health(profile)
        profile["oxygen"] = get_max_oxygen(profile)

        save_profile(uid, profile)

        embed = discord.Embed(
            title="🚀 Welcome to [GAME NAME]!",
            description=(
                "Your journey begins now. Earn Scrap, craft gear, and explore the stars.\n\n"
                "Starter commands:\n"
                "• scan — fight local enemies for XP and drops\n"
                "• work — gather basic materials via planet jobs\n"
                "• research — answer questions for bonus XP\n"
                "• explore — discover points of interest\n\n"
                "Next step: run `!tutorial` for a quick guide."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Tip: Use !commands to see what you can do.")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Start(bot))