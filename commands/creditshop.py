import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.players import save_profile
from core.shared import load_json
from core.bank import ensure_bank
from core.guards import require_no_lock

CREDITSHOP_FILE = "data/creditshop.json"

def load_cshop():
    data = load_json(CREDITSHOP_FILE) or {}
    # Support both {"items": {...}} and flat {"bank": {...}}
    items = data.get("items")
    if isinstance(items, dict):
        return items
    return data

def resolve_item(query: str, items: dict):
    q = (query or "").strip().lower()
    for item_id, cfg in items.items():
        name = str(cfg.get("name", item_id)).lower()
        aliases = [a.lower() for a in (cfg.get("aliases") or [])]
        if q in {item_id.lower(), name} | set(aliases):
            return item_id, cfg
    return None, None

class CreditShop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="creditshop", aliases=["cshop"])
    @requires_profile()
    async def creditshop(self, ctx):
        items = load_cshop()
        if not items:
            await ctx.send("The Credit Shop is currently empty.")
            return

        embed = discord.Embed(
            title="🪙 Credit Shop",
            description=f"Your Credits: {int(ctx.player.get('Credits', 0)):,}",
            color=discord.Color.gold(),
        )
        embed.set_footer(text="Use !creditbuy or !cbuy <item> to purchase an item.")
        for item_id, cfg in items.items():
            name = cfg.get("name", item_id)
            price = int(cfg.get("price", 0))
            desc = cfg.get("description", "")
            embed.add_field(name=f"{name} — {price} Credits", value=desc or "-", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="creditbuy", aliases=["cbuy"])
    @requires_profile()
    @require_no_lock()
    async def creditbuy(self, ctx, *, item_query: str):
        items = load_cshop()
        item_id, cfg = resolve_item(item_query, items)
        if not cfg:
            await ctx.send("❌ That item is not sold in the Credit Shop.")
            return

        price = int(cfg.get("price", 0))
        credits = int(ctx.player.get("Credits", 0))
        if credits < price:
            await ctx.send(f"❌ Not enough Credits. You need {price} (have {credits}).")
            return

        # Handle purchases
        if item_id == "bank":
            bank = ensure_bank(ctx.player)
            if bank.get("unlocked"):
                await ctx.send("✅ Your Bank is already unlocked.")
                return
            ctx.player["Credits"] = credits - price
            bank["unlocked"] = True
            ctx.player["bank"] = bank
            save_profile(ctx.author.id, ctx.player)
            await ctx.send("🏦 Bank unlocked! Use !deposit and !withdraw to manage your balance.")
            return

        if item_id in ("ship_token", "shiptoken", "ship-token"):
            # Add one Ship Token to inventory
            inv = ctx.player.get("inventory", {}) or {}
            inv["ship_token"] = int(inv.get("ship_token", 0)) + 1
            ctx.player["inventory"] = inv
            ctx.player["Credits"] = credits - price
            save_profile(ctx.author.id, ctx.player)
            await ctx.send("🪙 Purchased 1x Ship Token. Use it with `!use ship token` before `!ship refit` to keep your type for one refit.")
            return

        # Fallback (unknown-but-configured items): add an entry in inventory by its id
        inv = ctx.player.get("inventory", {}) or {}
        inv[item_id] = int(inv.get(item_id, 0)) + 1
        ctx.player["inventory"] = inv
        ctx.player["Credits"] = credits - price
        save_profile(ctx.author.id, ctx.player)
        await ctx.send(f"✅ Purchased 1x {cfg.get('name', item_id)}.")
        
async def setup(bot):
    await bot.add_cog(CreditShop(bot))