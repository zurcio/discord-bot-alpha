import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio

from dynamic_loader import load_all_extensions

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=["!", "spc "], intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"\n[🚀] Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"[💡] Connected to {len(bot.guilds)} servers")
    print(f"[💬] Loaded commands: {[c.name for c in bot.commands]}")
    print("-" * 50)


# Basic ping test command (always keep one internal command for diagnostics)
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@commands.is_owner()
@bot.command(name="reload")
async def reload_extensions(ctx):
    await load_all_extensions(ctx.bot)
    await ctx.send("♻️ Reloaded all extensions.")

async def main():
    async with bot:
        await load_all_extensions(bot)
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
