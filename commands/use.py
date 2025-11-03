## ====== USE ITEM COMMAND ======
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.utils import get_max_oxygen, get_max_health
from core.shared import load_json, save_json
from core.items import load_items, find_item, get_item_by_id, iterate_all_items
from core.constants import ITEMS_FILE
from core.guards import require_no_lock
from core.players import save_profile


class Use(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="use")
    @requires_profile()
    @require_no_lock()
    async def use(self, ctx, item_query: str, amount: int = 1):
        """Use one or more items from your inventory (by name or alias). Example: !use med 3"""
        player = ctx.player
        inventory = player.get("inventory", {})
        items = load_json(ITEMS_FILE)

        item_query = item_query.lower().strip()
        amount = max(1, amount)

        # NEW: Ship Token special-case (not in items.json)
        if item_query in ("ship token", "ship_token", "ship-token", "token", "shiptoken"):
            have = int(inventory.get("ship_token", 0))
            if have <= 0:
                await ctx.send(f"{ctx.author.mention}, you don’t have a Ship Token.")
                return
            inventory["ship_token"] = have - 1
            if inventory["ship_token"] <= 0:
                del inventory["ship_token"]
            # Arm next refit to keep type (one-time)
            ship = player.get("ship", {}) or {}
            ship["lock_type_once"] = True
            player["ship"] = ship
            player["inventory"] = inventory
            save_profile(ctx.author.id, player)
            await ctx.send("🪙 Ship Token used. Your next `!ship refit` will keep your current ship type.")
            return

        # Search inventory by name/alias
        target_item_id = None
        target_item = None
        for inv_id, quantity in inventory.items():
            if quantity <= 0:
                continue

            item = find_item(items, inv_id)
            if not item:
                continue

            names = [item["name"].lower()] + [a.lower() for a in item.get("aliases", [])]
            if item_query in names:
                target_item_id = str(inv_id)
                target_item = item
                break

        if not target_item:
            await ctx.send(f"{ctx.author.mention}, you don’t have `{item_query}` in your inventory!")
            return

        available = inventory[target_item_id]
        use_count = min(amount, available)
        if use_count < amount:
            await ctx.send(f"{ctx.author.mention}, you only have {available} `{target_item['name']}` in your inventory.")

        total_gained = 0
        effect_type = target_item.get("effect")
        for _ in range(use_count):
            if effect_type == "restore_oxygen":
                old = player["oxygen"]
                max_oxy = get_max_oxygen(player)
                restore = min(target_item["restore"], max_oxy - player["oxygen"])
                if restore <= 0:
                    continue
                player["oxygen"] += restore
                total_gained += restore
            elif effect_type == "restore_health":
                old = player["health"]
                max_hp = get_max_health(player)
                restore = min(target_item["restore"], max_hp - player["health"])
                if restore <= 0:
                    continue
                player["health"] += restore
                total_gained += restore

            inventory[target_item_id] -= 1
            if inventory[target_item_id] <= 0:
                del inventory[target_item_id]
                break

        player["inventory"] = inventory
        save_profile(ctx.author.id, player)

        if effect_type == "restore_oxygen":
            await ctx.send(
                f"{ctx.author.mention} used {use_count} **{target_item['name']}** and restored {total_gained} oxygen! 🫁 "
                f"You now have {player.get('oxygen')}/{get_max_oxygen(player)}"
            )
        elif effect_type == "restore_health":
            await ctx.send(
                f"{ctx.author.mention} used {use_count} **{target_item['name']}** and restored {total_gained} health! :anatomical_heart: "
                f"You now have {player.get('health')}/{get_max_health(player)}"
            )
        else:
            await ctx.send(f"{ctx.author.mention}, **{target_item['name']}** had no effect!")

async def setup(bot):
    await bot.add_cog(Use(bot))
