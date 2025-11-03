from discord.ext import commands
from core.decorators import requires_profile
from core.shared import load_json
from core.constants import PLANETS_FILE
from core.guards import require_no_lock


class Travel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="travel")
    @requires_profile()
    @require_no_lock()
    async def travel(self, ctx, planet_id: int):
        """Travel to an unlocked planet."""
        player = ctx.player
        unlocked = player.get("max_unlocked_planet", 1)

        if planet_id > unlocked:
            await ctx.send(f"❌ You haven’t unlocked Planet {planet_id} yet.")
            return

        player["current_planet"] = planet_id
        planets = load_json(PLANETS_FILE)
        planet_name = planets.get(str(planet_id), {}).get("name", f"Planet {planet_id}")
        await ctx.send(f"🛸 You traveled to **{planet_name}**.")

async def setup(bot):
    await bot.add_cog(Travel(bot))