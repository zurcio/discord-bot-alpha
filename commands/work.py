from discord.ext import commands
from core.decorators import requires_profile, requires_oxygen, requires_planet
from systems.work_sys import handle_work
from core.guards import require_no_lock



class Work(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="scavenge", aliases=["scav"])
    @requires_profile()
    @requires_oxygen(10)
    @require_no_lock()
    async def scavenge(self, ctx):
        await handle_work(ctx, "scavenge")

    @commands.command(name="hack")
    @requires_profile()
    @requires_oxygen(10)
    @require_no_lock()
    async def hack(self, ctx):
        await handle_work(ctx, "hack")

    @commands.command(name="extract", aliases=["ext"])
    @requires_profile()
    @requires_oxygen(10)
    @requires_planet(3)
    @require_no_lock()
    async def extract(self, ctx):
        await handle_work(ctx, "extract")

    @commands.command(name="harvest", aliases=["harv"])
    @requires_profile()
    @requires_oxygen(10)
    @requires_planet(5)
    @require_no_lock()
    async def harvest(self, ctx):
        await handle_work(ctx, "harvest")

async def setup(bot):
    await bot.add_cog(Work(bot))