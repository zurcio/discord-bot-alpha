import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.utils import get_max_health
from core.players import save_profile
from core.constants import ITEMS_FILE
from core.shared import load_json
from core.guards import require_no_lock


class Heal(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="heal", aliases=["med", "usemed"])
    @requires_profile()
    @require_no_lock()
    async def heal(self, ctx):
        """
        Use a Medkit to restore health.
        Acts as a shortcut for '!use med'.
        """
        player = ctx.player
        inventory = player.get("inventory", {})
        items = load_json(ITEMS_FILE)

        # Try to find the medkit by name or ID
        medkit_id = None
        medkit_item = None
        for category, entries in items.items():
            for item_id, item in entries.items():
                if item.get("name", "").lower() == "medkit":
                    medkit_id = item_id
                    medkit_item = item
                    break
            if medkit_id:
                break

        if not medkit_id or medkit_id not in inventory or inventory[medkit_id] <= 0:
            await ctx.send(f"{ctx.author.mention}, you don’t have any Medkits to use!")
            return

        max_hp = get_max_health(player)
        current_hp = player.get("health", 0)

        if current_hp >= max_hp:
            await ctx.send(f"{ctx.author.mention}, your health is already full!")
            return

        # Heal logic — restore 50 HP (tweakable)
        heal_amount = 50
        new_hp = min(max_hp, current_hp + heal_amount)
        healed_for = new_hp - current_hp
        player["health"] = new_hp

        # Consume one Medkit
        inventory[medkit_id] -= 1
        if inventory[medkit_id] <= 0:
            del inventory[medkit_id]
        player["inventory"] = inventory

        save_profile(ctx.author.id, player)

        embed = discord.Embed(
            title="🩹 Medicating",
            description=f"You used a **Medkit** and healed for **{healed_for} HP**!",
            color=discord.Color.green()
        )
        embed.add_field(name="Current Health", value=f"{player['health']}/{max_hp} ❤️", inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Heal(bot))
