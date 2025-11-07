import math, json
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.guards import require_no_lock, set_lock, clear_lock
from core.players import load_profile, save_profile, get_scrap, set_scrap
from core.utils import parse_float_amount
from systems.commodities import get_quote

BASES = {"plasteel", "circuit", "plasma", "biofiber"}
FEE_RATE = 0.02

def _ensure_portfolio(p: dict) -> dict:
    port = p.get("commodities") or {}
    port.setdefault("positions", {})
    port.setdefault("realized_pnl", 0.0)
    p["commodities"] = port
    return port

class Market(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mbuy")
    @requires_profile()
    @require_no_lock()
    async def mbuy(self, ctx, base: str = None, amount: str = None):
        if not base or not amount:
            await ctx.send("Usage: !mbuy <plasteel|circuit|plasma|biofiber> <units|all>")
            return
        base = base.strip().lower()
        if base not in BASES:
            await ctx.send("Unknown commodity.")
            return

        uid = str(ctx.author.id)
        set_lock(uid, lock_type="market", allowed=set(), note=f"mbuy {base}")
        try:
            price = get_quote(base)
            if price <= 0:
                await ctx.send("Market price unavailable.")
                return

            # Preview using a snapshot
            snap = load_profile(uid) or {}
            scrap_snap = get_scrap(snap)
            if scrap_snap <= 0:
                await ctx.send("You have no Scrap.")
                return

            # Calculate max affordable units for validation
            max_units = scrap_snap / (price * (1.0 + FEE_RATE))
            units = parse_float_amount(amount, max_units)
            
            if units <= 0:
                await ctx.send("Amount must be positive. Use a number, 'all', 'half', or suffixes like '1.5m', '500k'.")
                return

            gross = units * price
            fee = gross * FEE_RATE
            total_cost = math.ceil(gross + fee)

            # Commit on a fresh profile (to avoid stale overwrite)
            prof = load_profile(uid) or {}
            port = _ensure_portfolio(prof)
            have = get_scrap(prof)

            # Clamp to current funds at commit time
            if total_cost > have:
                units = (have) / (price * (1.0 + FEE_RATE))
                units = max(0.0, round(units, 4))
                gross = units * price
                fee = gross * FEE_RATE
                total_cost = math.ceil(gross + fee)
                if units <= 0:
                    await ctx.send("Insufficient Scrap.")
                    return

            set_scrap(prof, have - total_cost)

            pos = port["positions"].get(base) or {"units": 0.0, "avg_cost": 0.0}
            new_units = pos["units"] + units
            if new_units > 0:
                pos["avg_cost"] = round(((pos["units"] * pos["avg_cost"]) + gross) / new_units, 4)
            pos["units"] = round(new_units, 4)
            port["positions"][base] = pos
            prof["commodities"] = port

            save_profile(uid, prof)
            await ctx.send(f"✅ Bought {units:.4f} {base} @ {price:.2f} (fee {fee:.0f}). New position: {pos['units']:.4f}")
        finally:
            clear_lock(uid)

    @commands.command(name="msell")
    @requires_profile()
    @require_no_lock()
    async def msell(self, ctx, base: str = None, amount: str = None):
        if not base or not amount:
            await ctx.send("Usage: !msell <plasteel|circuit|plasma|biofiber> <units|all>")
            return
        base = base.strip().lower()
        if base not in BASES:
            await ctx.send("Unknown commodity.")
            return

        uid = str(ctx.author.id)
        set_lock(uid, lock_type="market", allowed=set(), note=f"msell {base}")
        try:
            price = get_quote(base)
            if price <= 0:
                await ctx.send("Market price unavailable.")
                return

            # Commit on fresh profile
            prof = load_profile(uid) or {}
            port = _ensure_portfolio(prof)
            pos = port["positions"].get(base) or {"units": 0.0, "avg_cost": 0.0}
            held = float(pos.get("units", 0.0))
            if held <= 0:
                await ctx.send(f"You hold no {base}.")
                return

            units = parse_float_amount(amount, held)
            
            if units <= 0:
                await ctx.send("Amount must be positive. Use a number, 'all', 'half', or suffixes like '1.5m', '500k'.")
                return

            gross = units * price
            fee = gross * FEE_RATE
            proceeds = math.floor(gross - fee)

            avg_cost = float(pos.get("avg_cost", 0.0))
            cost_basis = units * avg_cost
            realized = gross - fee - cost_basis

            # Update position
            pos["units"] = round(held - units, 4)
            if pos["units"] <= 0:
                pos["units"] = 0.0
                pos["avg_cost"] = 0.0
            port["positions"][base] = pos
            port["realized_pnl"] = round(float(port.get("realized_pnl", 0.0)) + float(realized), 2)
            prof["commodities"] = port

            # Credit scrap
            set_scrap(prof, get_scrap(prof) + proceeds)

            save_profile(uid, prof)
            sign = "profit" if realized >= 0 else "loss"
            await ctx.send(f"✅ Sold {units:.4f} {base} @ {price:.2f} (fee {fee:.0f}). Proceeds {proceeds:,}. Realized {sign}: {realized:+.0f}. Remaining: {pos['units']:.4f}")
        finally:
            clear_lock(uid)

    @commands.command(name="mportfolio", aliases=["mpositions"])
    @requires_profile()
    async def mportfolio(self, ctx):
        prof = load_profile(str(ctx.author.id)) or {}
        port = (prof.get("commodities") or {})
        positions = (port.get("positions") or {})
        if not positions:
            await ctx.send("You have no commodity positions. Use !mbuy to get started.")
            return
        lines, total_upl = [], 0.0
        for base, pos in positions.items():
            units = float(pos.get("units", 0.0))
            if units <= 0:
                continue
            avg = float(pos.get("avg_cost", 0.0))
            px = get_quote(base)
            value = units * px
            upl = (px - avg) * units
            total_upl += upl
            lines.append(f"{base:<9} {units:>10.4f}  avg {avg:>7.2f}  px {px:>7.2f}  UPL {upl:+.0f}  val {value:,.0f}")
        realized = float(port.get("realized_pnl", 0.0))
        desc = "commodity      units      avg       price     UPL      value\n" + "\n".join(lines)
        desc += f"\n\nRealized PnL: {realized:+.0f} | Unrealized PnL: {total_upl:+.0f}"
        await ctx.send(f"```{desc}```")

async def setup(bot):
    await bot.add_cog(Market(bot))