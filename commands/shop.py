import time
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.constants import SHOP_FILE, ITEMS_FILE
from core.shared import load_json
from core.items import get_item_by_id
from core.cooldowns import check_and_set_cooldown
from core.guards import require_no_lock
from systems.ship_sys import grant_starter_ship
from core.players import save_profile

# Helper: dynamic keycard price per current planet
def _keycard_price_for_player(player: dict) -> int:
    planet_id = int(player.get("current_planet") or player.get("max_unlocked_planet", 1))
    base_cost = 5000
    return base_cost * (planet_id ** 2)

def _trim(s: str, limit: int = 1024) -> str:
    return s if len(s) <= limit else (s[: max(0, limit - 2)] + "…")

class Shop(commands.Cog):    
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="shop")
    @requires_profile()
    @require_no_lock()
    async def shop(self, ctx):
        """View items available in the shop, shown in two wide columns."""
        player = ctx.player
        shop_data = load_json(SHOP_FILE) or {}
        items_data = load_json(ITEMS_FILE) or {}

        Scrap = player.get("Scrap", 0)

        embed = discord.Embed(
            title="🛒 Galactic Shop",
            description=f"Your Scrap: 💳 {Scrap}\nBrowse and purchase items using `!buy <name/alias>`.",
            color=discord.Color.blue()
        )

        # Build category sections as blocks of text
        sections: list[tuple[str, str]] = []  # (category_display_name, block_text)

        for category, items in shop_data.items():
            lines = []
            for item_id, shop_entry in items.items():
                item = get_item_by_id(items_data, item_id)
                if not item:
                    name = f"Unknown Item ({item_id})"
                    description = shop_entry.get("description", "No description.")
                    aliases = []
                    item_type = (shop_entry.get("type") or "").lower()
                else:
                    name = item.get("name", f"Unknown Item ({item_id})")
                    description = shop_entry.get("description") or item.get("description", "No description.")
                    aliases = item.get("aliases", [])
                    item_type = (item.get("type") or shop_entry.get("type") or "").lower()

                # Price (dynamic for keycard)
                if item_type in {"keycard"} or category.lower() == "keycard" or (shop_entry.get("type") or "").lower() in {"key", "keycard"}:
                    price_each = _keycard_price_for_player(player)
                    price_str = f"{price_each:,} (your planet price)"
                else:
                    price_each = int(shop_entry.get("price", 0) or 0)
                    price_str = f"{price_each:,}" if price_each else "N/A"

                # Show aliases as buy examples
                alias_str = ""
                if aliases:
                    alias_examples = [f"`!buy {a}`" for a in aliases[:3]]
                    alias_str = f"\n*Try: {' / '.join(alias_examples)}*"

                # Optional limit display
                limit = shop_entry.get("limit")
                limit_str = f" • Limit: {limit}" if limit else ""

                lines.append(f"**{name}** — 💳 {price_str}{limit_str}\n{description}{alias_str}")

            if lines:
                block = f"__{category.capitalize()}__\n" + "\n\n".join(lines)
                sections.append((category.capitalize(), block))

        if not sections:
            await ctx.send("The shop is currently empty.")
            return

        # Distribute sections across two columns by current character length
        left, right = [], []
        left_len = right_len = 0
        for _, block in sections:
            # Decide which column to place this block in (greedy balance)
            if left_len <= right_len:
                left.append(block)
                left_len += len(block) + 2
            else:
                right.append(block)
                right_len += len(block) + 2

        left_text = _trim("\n\n".join(left)) if left else "-"
        right_text = _trim("\n\n".join(right)) if right else "-"

        embed.add_field(name="Aisle I", value=left_text or "-", inline=True)
        embed.add_field(name="Aisle II", value=right_text or "-", inline=True)

        await ctx.send(embed=embed)

class Buy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="buy")
    @requires_profile()
    @require_no_lock()
    async def buy(self, ctx, item_name: str, amount: int = 1):
        """Buy an item or lootbox."""
        player = ctx.player
        shop = load_json(SHOP_FILE) or {}
        items = load_json(ITEMS_FILE) or {}

        query = item_name.lower().strip()
        amount = max(1, min(amount, 100))
        found_item = None
        found_category = None

        for category, entries in shop.items():
            for item_id, data in entries.items():
                item_obj = get_item_by_id(items, item_id)
                if not item_obj:
                    continue
                names = [str(item_id).lower(), item_obj["name"].lower()] + [a.lower() for a in item_obj.get("aliases", [])]
                if query in names:
                    found_item = (item_id, item_obj, data)
                    found_category = category
                    break
            if found_item:
                break

        if not found_item:
            await ctx.send(f"{ctx.author.mention} That item doesn’t exist.")
            return

        item_id, item_obj, shop_entry = found_item

        # Detect supply crate early and clamp amount to 1 to prevent cooldown bypass
        is_supply_crate_item = (item_obj.get("type") or "").lower() == "supply_crate"
        if is_supply_crate_item and amount != 1:
            amount = 1

        # Boss keycard: limit to 1 owned at a time, price scales with CURRENT planet
        is_keycard = (
            (item_obj.get("type") or "").lower() == "keycard"
            or (found_category or "").lower() == "keycard"
            or (shop_entry.get("type") or "").lower() in {"key", "keycard"}
        )
        if is_keycard:
            inv = player.get("inventory", {}) or {}
            owned = int(inv.get(item_id, 0) or 0)
            if owned >= 1:
                await ctx.send(f"{ctx.author.mention} You already have a boss keycard. Use it in a bossfight before buying another.")
                return
            if amount > 1:
                amount = 1
            price_each = _keycard_price_for_player(player)
        else:
            # Regular items
            price_each = int(shop_entry.get("price", 0) or 0)

        total_price = price_each * amount
        if player.get("Scrap", 0) < total_price:
            await ctx.send(f"{ctx.author.mention} Not enough Scrap (need {total_price:,}).")
            return

        # Supply Crate cooldown: allow only one every 3 hours; amount already clamped to 1 above
        is_supply_crate = is_supply_crate_item
        if is_supply_crate:
            if not await check_and_set_cooldown(ctx, "supply_crate", 10800):
                return

        # Starter ship special-case
        if item_id == "starter_ship":
            if player.get("ship", {}).get("owned"):
                await ctx.send(f"{ctx.author.mention}, you already own a ship.")
                return
            # deduct cost as usual...
            grant_starter_ship(player)
            save_profile(ctx.author.id, player)
            await ctx.send(f"🛸 {ctx.author.mention} acquired a Starter Ship! Use `!ship` to view it.")
            return

        # Deduct and add item
        player["Scrap"] = player.get("Scrap", 0) - total_price
        player.setdefault("inventory", {})
        player["inventory"][item_id] = int(player["inventory"].get(item_id, 0)) + amount

        await ctx.send(f"{ctx.author.mention} bought **{amount}x {item_obj['name']}** for 💳 {total_price:,} Scrap!")
        save_profile(ctx.author.id, player)


async def setup(bot):
    await bot.add_cog(Shop(bot))
    await bot.add_cog(Buy(bot))