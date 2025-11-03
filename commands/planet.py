import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.shared import load_json
from core.guards import require_no_lock
from core.constants import PLANETS_FILE, ENEMIES_FILE


class PlanetCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="planet", aliases=["pl"])
    @requires_profile()
    @require_no_lock()
    async def planet(self, ctx):
        """Show info about your current planet."""
        player = ctx.player
        planet_id = str(player.get("current_planet", 1))

        planets_data = load_json(PLANETS_FILE)
        planet = planets_data.get(planet_id)

        enemies_data = load_json(ENEMIES_FILE).get(f"P{planet_id}E", {})
        basic_enemies = [e["name"] for e in enemies_data.values() if e.get("category") == "basic"]
        elite_enemies = [e["name"] for e in enemies_data.values() if e.get("category") == "elite"]


        if not planet:
            await ctx.send("❌ Current planet data not found.")
            return

        # Use requirements_names directly from JSON
        req_names = planet.get("requirements", [])
        if not req_names:
            req_names = ["None"]

        # Create a rich embed
        embed = discord.Embed(
            title=f"🪐 Planet {planet_id}: {planet['name']}",
            description=planet.get("description", "No description available."),
            color=discord.Color.blurple()
        )

        # Basic planet info
        embed.add_field(name="Boss", value=f"👾 {planet.get('boss', 'Unknown')}", inline=True)
        embed.add_field(name="Level Requirement", value=planet.get("level_requirement", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # spacer for formatting

        # Requirements
        embed.add_field(
            name="Required Gear for Boss Fight",
            value=", ".join(req_names),
            inline=False
        )

        # Possible Enemy Encounters
        embed.add_field(
            name="Possible Enemy Encounters",
            value=f"👶 Scan: {', '.join(basic_enemies) if basic_enemies else 'None'}\n🦾 Explore: {', '.join(elite_enemies) if elite_enemies else 'None'}",
            inline=False
        )

        # Player info
        embed.add_field(
            name="Your Progress",
            value=f"🌍 Current Planet: **{planet_id}**\n🔓 Max Unlocked: **{player.get('max_unlocked_planet', 1)}**",
            inline=False
        )

        # Optional visuals
        embed.set_thumbnail(url="https://i.imgur.com/yxR0P4H.png")  # Replace with your own
        embed.set_footer(
            text=f"Requested by {ctx.author.name}",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(PlanetCommand(bot))
