    # ====== EQUIP COMMAND ======
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.shared import load_json
from core.players import calculate_combat_stats, save_profile
from core.items import load_items, find_item, get_item_by_id, iterate_all_items
from core.guards import require_no_lock
from core.constants import ITEMS_FILE


class Equip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @requires_profile()
    @require_no_lock()
    async def equip(self, ctx, *, item_name: str = None):
        """Equip a weapon or armor from your inventory by name or alias."""
        if not item_name:
            await ctx.send(
                f"{ctx.author.mention}, usage: `!equip <item name>`\n"
                "Equip a weapon or armor from your inventory by name or alias."
            )
            return

        player = ctx.player
        inventory = player.get("inventory", {})
        items = load_json(ITEMS_FILE)
        item_name = item_name.lower()

        # Search player inventory for matching item
        target_id = None
        target_item = None
        for category, item_dict in items.items():
            for item_id, item in item_dict.items():
                if str(item_id) not in inventory or inventory[str(item_id)] <= 0:
                    continue
                names = [item.get("name","").lower()] + [a.lower() for a in item.get("aliases", [])]
                if item_name in names:
                    target_id = item_id
                    target_item = item
                    break
            if target_item:
                break  # stop after finding the first valid item

        if not target_item:
            await ctx.send(f"{ctx.author.mention}, you don’t have that item in your inventory!")
            return

        # Only weapons/armor can be equipped
        if target_item.get("type") not in ["weapon", "armor"]:
            await ctx.send(f"{ctx.author.mention}, you can’t equip {target_item.get('name','that item')}!")
            return

        # Prevent equipping if slot is already occupied
        slot = target_item["type"]  # "weapon" or "armor"
        equipped = player.setdefault("equipped", {"weapon": None, "armor": None})
        if equipped.get(slot):
            # Tell the user to sell their equipped gear to de-equip
            current_id = equipped[slot]
            current_item = get_item_by_id(items, current_id) or {}
            current_name = current_item.get("name", str(current_id))
            sell_keyword = "weapon" if slot == "weapon" else "suit"
            await ctx.send(
                f"{ctx.author.mention}, you already have **{current_name}** equipped.\n"
                f"Sell your current {slot} with `!sell {sell_keyword}` to unequip it, then try `!equip {item_name}` again."
            )
            return

        # Equip item
        equipped[slot] = target_id
        save_profile(player["id"], player)

        # Calculate effective stats dynamically
        stats = calculate_combat_stats(player)

        await ctx.send(
            f"{ctx.author.mention} equipped **{target_item['name']}** "
            f"→ Attack: {stats['attack']} ⚔️ | Defense: {stats['defense']} 🛡️"
        )

async def setup(bot):
    await bot.add_cog(Equip(bot))