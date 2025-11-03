from discord.ext import commands

class TestShop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def testshop(self, ctx):
        await ctx.send("Test shop works!")

async def setup(bot):
    print("Adding TestShop cog")
    await bot.add_cog(TestShop(bot))