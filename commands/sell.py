from discord.ext import commands
from core.decorators import requires_profile
from core.shared import load_json
from core.players import save_profile
from core.guards import require_no_lock
from core.constants import ITEMS_FILE
from core.skills_hooks import trader_effects, award_skill, trader_xp_for_item

def find_item_by_query(items_data, query):
    query = query.lower().strip()
    for category in items_data:
        for item_id, item in items_data[category].items():
            names = [item["name"].lower()] + [a.lower() for a in item.get("aliases", [])]
            if query in names or query == item_id.lower():
                return category, item_id, item
    return None, None, None

def _clear_enhancement_if_none_left(player: dict, item_id: str):
    """Remove enhancement entry if the player has no copies left and it's not equipped."""
    item_id = str(item_id)
    inv = player.get("inventory", {}) or {}
    qty = int(inv.get(item_id, 0))
    equipped = player.get("equipped", {}) or {}
    still_equipped = (str(equipped.get("weapon")) == item_id) or (str(equipped.get("armor")) == item_id)
    if qty <= 0 and not still_equipped:
        enh = player.get("enhancements", {}) or {}
        if item_id in enh:
            del enh[item_id]
            player["enhancements"] = enh

def _sanitize_enhancements(player: dict):
    """
    Enforce enhancement rules:
    - Tinker unlocks at planet 2; if locked, remove all enhancements.
    - Keep at most 2 enhancements total: only for currently equipped weapon/armor.
    """
    enh = dict(player.get("enhancements") or {})
    if not enh:
        return
    # Tinker unlock check (planet 2+)
    p = int(player.get("max_unlocked_planet") or player.get("current_planet") or 1)
    if p < 2:
        if enh:
            player["enhancements"] = {}
        return

    equipped = player.get("equipped", {}) or {}
    allowed = set()
    wid = equipped.get("weapon")
    aid = equipped.get("armor")
    if wid:
        allowed.add(str(wid))
    if aid:
        allowed.add(str(aid))

    changed = False
    for k in list(enh.keys()):
        if k not in allowed:
            enh.pop(k, None)
            changed = True

    if changed:
        player["enhancements"] = enh

class Sell(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sell")
    @requires_profile()
    @require_no_lock()
    async def sell(self, ctx, *args):
        """Sell items for Scrap. Usage: !sell <item name|weapon|suit> [amount|half|all]"""
        if not args:
            await ctx.send(f"{ctx.author.mention}, please specify an item to sell.")
            return

        # Parse item name and amount
        if len(args) == 1:
            item_query = args[0]
            amount = "1"
        else:
            last = args[-1].lower()
            if last in ("all", "half") or last.isdigit():
                item_query = " ".join(args[:-1])
                amount = last
            else:
                item_query = " ".join(args)
                amount = "1"

        player = ctx.player
        inventory = player.get("inventory", {})
        items_data = load_json(ITEMS_FILE) or {}
        equipped = player.get("equipped", {}) or {}

        # Skill: Trader sell multiplier
        sell_mult = float(trader_effects(player).get("sell_price_mult", 1.0))

        # Special handling: selling equipped gear via slot keyword
        slot_query = item_query.lower().strip()
        if slot_query in ("weapon", "armor", "suit"):
            slot = "armor" if slot_query in ("armor", "suit") else "weapon"
            equipped_id = (equipped or {}).get(slot)
            if not equipped_id:
                await ctx.send(f"{ctx.author.mention}, you don’t have a {slot} equipped.")
                return

            # Look up the equipped item by id across all categories
            _, _, item = find_item_by_query(items_data, str(equipped_id))
            if not item:
                await ctx.send(f"{ctx.author.mention}, your equipped {slot} could not be found in the item database.")
                return

            # Ensure it is sellable
            if not item.get("sellable", False):
                await ctx.send(f"{ctx.author.mention}, **{item.get('name','This item')}** cannot be sold.")
                return

            # Force sell amount to 1 for equipped gear
            owned = int(inventory.get(str(equipped_id), 0))
            if owned < 1:
                owned = 1

            base_value = int(item.get("value", 0))
            scrap_gain = int(round(base_value * sell_mult))

            # Update inventory for one sold copy
            if str(equipped_id) in inventory:
                inventory[str(equipped_id)] = max(0, owned - 1)
                if inventory[str(equipped_id)] <= 0:
                    del inventory[str(equipped_id)]
            player["inventory"] = inventory

            # Unequip the slot
            player.setdefault("equipped", {})[slot] = None

            # Clear enhancement if none left, then sanitize globally
            _clear_enhancement_if_none_left(player, str(equipped_id))
            _sanitize_enhancements(player)

            # Add Scrap (with Trader multiplier)
            player["Scrap"] = player.get("Scrap", 0) + scrap_gain

            # Add Scrap (with Trader multiplier)
            player["Scrap"] = player.get("Scrap", 0) + scrap_gain

            # Trader XP — exact per unit sold (weapons/armor likely 0 unless mapped)
            per_unit_xp = trader_xp_for_item(str(equipped_id), item.get("name"))
            total_trader_xp = per_unit_xp  # selling exactly one
            lvl, ups = award_skill(ctx, "trader", total_trader_xp) if total_trader_xp > 0 else (0, 0)

            note = (
                f" • 🎲 Trader +{total_trader_xp} XP" + (f" (L{lvl} +{ups})" if ups > 0 else "")
                if total_trader_xp > 0 else ""
            )
            await ctx.send(
                f"{ctx.author.mention} sold their equipped **{item['name']}** ({slot}) for {scrap_gain} Scrap.{note} "
                f"You can now equip a new {slot} with `!equip <name>`."
            )
            save_profile(ctx.author.id, player)
            return

        # Normal item selling path (by name or id)
        category, item_id, item = find_item_by_query(items_data, item_query)
        if not item:
            await ctx.send(f"{ctx.author.mention}, item `{item_query}` not found.")
            return

        if not item.get("sellable", False):
            await ctx.send(f"{ctx.author.mention}, **{item['name']}** cannot be sold.")
            return

        owned = int(inventory.get(item_id, 0))
        # Determine if this item is gear and currently equipped
        item_type = str(item.get("type", "")).lower()
        slot_for_item = "weapon" if item_type == "weapon" else ("armor" if item_type in ("armor", "suit") else None)
        is_equipped_match = slot_for_item and str(equipped.get(slot_for_item)) == str(item_id)

        if owned < 1:
            if is_equipped_match:
                owned = 1
            else:
                await ctx.send(f"{ctx.author.mention}, you don’t have any **{item['name']}** to sell.")
                return

        # Parse amount
        if amount == "all":
            sell_amount = owned
        elif amount == "half":
            sell_amount = max(1, owned // 2)
        else:
            try:
                sell_amount = int(amount)
            except ValueError:
                await ctx.send(f"{ctx.author.mention}, invalid amount `{amount}`.")
                return
            sell_amount = min(sell_amount, owned)
            if sell_amount < 1:
                await ctx.send(f"{ctx.author.mention}, you must sell at least one item.")
                return

        # Compute remaining before applying to know if we must unequip
        remaining_after = owned - sell_amount

        # Apply inventory changes
        if item_id in inventory:
            inventory[item_id] = max(0, inventory[item_id] - sell_amount)
            if inventory[item_id] <= 0:
                del inventory[item_id]
        player["inventory"] = inventory

        # If this was the equipped item and no copies remain, unequip it
        unequipped_note = ""
        if is_equipped_match and remaining_after <= 0:
            player.setdefault("equipped", {})[slot_for_item] = None
            unequipped_note = f" Your {slot_for_item} slot was unequipped."

        # Clear enhancement if none left (after potential unequip), then sanitize globally
        _clear_enhancement_if_none_left(player, item_id)
        _sanitize_enhancements(player)

        # Calculate Scrap gain with Trader multiplier
        base_value_each = int(item.get("value", 0))
        base_total = base_value_each * sell_amount
        scrap_gain = int(round(base_total * sell_mult))
        player["Scrap"] = player.get("Scrap", 0) + scrap_gain

        # Trader XP — exact per item, times quantity sold
        per_unit_xp = trader_xp_for_item(item_id, item.get("name"))
        total_trader_xp = per_unit_xp * sell_amount
        lvl, ups = award_skill(ctx, "trader", total_trader_xp) if total_trader_xp > 0 else (0, 0)
        xp_note = (
            f" • 🎲 Trader +{total_trader_xp} XP" + (f" (L{lvl} +{ups})" if ups > 0 else "")
            if total_trader_xp > 0 else ""
        )

        await ctx.send(
            f"{ctx.author.mention} sold {sell_amount}x **{item['name']}** for {scrap_gain} Scrap!{unequipped_note}{xp_note}"
        )
        save_profile(ctx.author.id, player)


async def setup(bot):
    await bot.add_cog(Sell(bot))