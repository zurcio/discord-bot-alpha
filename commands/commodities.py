import discord
from discord.ext import commands
from systems.commodities import ensure_started, _load_state

def _spark(history):
    vals = [p.get("price", 0) for p in history[-20:]] or [0]
    lo, hi = (min(vals), max(vals))
    if hi == lo: return "▁" * len(vals)
    blocks = "▁▂▃▄▅▆▇█"
    out = []
    for v in vals:
        idx = int((v - lo) / (hi - lo) * (len(blocks) - 1))
        out.append(blocks[idx])
    return "".join(out)

class Commodities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ensure_started()

    @commands.command(name="commodities", aliases=["market"])
    async def commodities(self, ctx):
        st = _load_state()
        bases = st.get("bases", {})
        lines = []
        order = ["plasteel", "circuit", "plasma", "biofiber"]
        for base in order:
            b = bases.get(base) or {}
            total = int(b.get("total", 0))
            price = float(b.get("price", 0.0))
            pct = b.get("last_pct", 0.0)
            hist = b.get("history", [])
            trend = _spark(hist)
            sign = "▲" if pct > 0 else ("▼" if pct < 0 else "•")
            lines.append(f"{base:<9} {total:>12,}  {price:>9.2f}  {sign} {pct:>6.2f}%  {trend}")
        desc = "commodity      owned (base)     price      Δ%   24h price trend\n" + "\n".join(lines) if lines else "No data yet."
        embed = discord.Embed(title="📦 Galactic Commodities", description=f"```{desc}```", color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.command(name="commodity")
    async def commodity(self, ctx, base: str = None):
        if not base:
            await ctx.send("Usage: !commodity <plasteel|circuit|plasma|biofiber>")
            return
        base = base.strip().lower()
        st = _load_state()
        b = (st.get("bases") or {}).get(base)
        if not b:
            await ctx.send("Unknown commodity.")
            return
        total = int(b.get("total", 0))
        price = float(b.get("price", 0.0))
        trend = _spark(b.get("history", []))
        embed = discord.Embed(
            title=f"📈 {base.capitalize()}",
            description=f"Owned (base): {total:,}\nPrice: {price:.2f}\n24h price: {trend}",
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Commodities(bot))