import discord
from discord.ext import commands
from core.players import load_profile
from core.guards import require_no_lock


class Tutorial(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="tutorial", aliases=["guide", "helpme"])
    @require_no_lock()
    async def tutorial(self, ctx):
        """Get a quick guide to the game."""
        uid = str(ctx.author.id)
        profile = load_profile(uid)
        if not profile:
            await ctx.send(f"{ctx.author.mention}, you need to register first! Use `!start` to create your profile.")
            return

        embed = discord.Embed(
            title="📚 [GAME NAME] Tutorial",
            description=(
                "Welcome to [GAME NAME]! Here's a quick guide to get you started:\n\n"
                "Use commands by typing `!<command>` or `spc <command>` in the chat. Here are some key commands to know:\n\n"
                "1. **scan** - Engage in combat with local enemies to earn XP and item drops.\n"
                "2. **work** - Perform jobs on your current planet to gather basic materials.\n"
                "**work** is performed by subcommands like `!scavenge` and `!hack`.\n"
                "3. **research** - Answer questions and complete tasks for bonus XP.\n"
                "4. **explore** - Discover points of interest on your planet for rewards.\n\n"
                "Additional Commands:\n"
                "• `!profile` - View your player profile and stats.\n"
                "• `!inventory` - Check your inventory for items and equipment.\n"
                "• `!equip <item>` - Equip a weapon or armor from your inventory.\n"
                "• `!craft <item>` - Craft new items using materials you've gathered.\n"
                "• `!recipes` - View available crafting recipes.\n"
                "• `!travel <planet>` - Move to a different planet once unlocked.\n\n"
                "Tips:\n"
                "- Regularly check your health and oxygen levels during exploration and combat.\n"
                "- Upgrade your gear to improve your chances in tougher battles.\n"
                "- Join our community server for support, tips, and events!\n\n"
                "For a full list of commands, use `!commands`."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Good luck, explorer! 🚀")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Tutorial(bot))