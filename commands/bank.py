import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.players import save_profile
from core.guards import require_no_lock
from core.bank import ensure_bank, compute_bank_boost_percent, bank_xp_multiplier, maybe_apply_daily_interest  # CHANGED

def _parse_amount(arg: str | None, available: int) -> int:
    if not arg:
        return 0
    t = str(arg).lower()
    if t == "all":
        return int(available)
    if t == "half":
        return max(1, int(available // 2))
    try:
        n = int(t.replace(",", ""))
    except Exception:
        return 0
    return max(0, min(n, int(available)))

class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="deposit", aliases=["dep"])
    @requires_profile()
    @require_no_lock()
    async def deposit(self, ctx, amount: str = None):
        """Deposit Scrap into your bank: !deposit <number|all|half>"""
        player = ctx.player
        bank = ensure_bank(player)
        if not bank.get("unlocked", False):
            await ctx.send(f"{ctx.author.mention} You have not unlocked the Bank.")
            return

        # Apply any pending daily interest first
        gained = maybe_apply_daily_interest(player)
        if gained > 0:
            save_profile(ctx.author.id, player)

        available = int(player.get("Scrap", 0))
        amt = _parse_amount(amount, available)
        if amt <= 0:
            await ctx.send(f"{ctx.author.mention} Nothing to deposit. Usage: !deposit <number|all|half>")
            return

        player["Scrap"] = available - amt
        bank["balance"] = int(bank.get("balance", 0)) + amt
        player["bank"] = bank
        save_profile(ctx.author.id, player)

        total_mult = bank_xp_multiplier(player)
        pct = f"{(total_mult - 1.0)*100:.2f}%"
        msg_extra = f" Daily interest applied: +{gained:,}." if gained > 0 else ""
        await ctx.send(f"🏦 Deposited {amt:,} Scrap. Bank Balance: {bank['balance']:,}.{msg_extra} XP Boost: {pct}")

    @commands.command(name="withdraw", aliases=["wd"])
    @requires_profile()
    @require_no_lock()
    async def withdraw(self, ctx, amount: str = None):
        """Withdraw Scrap from your bank: !withdraw <number|all|half>"""
        player = ctx.player
        bank = ensure_bank(player)
        if not bank.get("unlocked", False):
            await ctx.send(f"{ctx.author.mention} You have not unlocked the Bank.")
            return

        # Apply any pending daily interest first
        gained = maybe_apply_daily_interest(player)
        if gained > 0:
            save_profile(ctx.author.id, player)

        available = int(bank.get("balance", 0))
        amt = _parse_amount(amount, available)
        if amt <= 0:
            await ctx.send(f"{ctx.author.mention} Nothing to withdraw. Usage: !withdraw <number|all|half>")
            return

        bank["balance"] = available - amt
        player["Scrap"] = int(player.get("Scrap", 0)) + amt
        player["bank"] = bank
        save_profile(ctx.author.id, player)

        total_mult = bank_xp_multiplier(player)
        pct = f"{(total_mult - 1.0)*100:.2f}%"
        msg_extra = f" Daily interest applied: +{gained:,}." if gained > 0 else ""
        await ctx.send(f"🏦 Withdrew {amt:,} Scrap. Bank Balance: {bank['balance']:,}.{msg_extra} XP Boost: {pct}")

async def setup(bot):
    await bot.add_cog(Bank(bot))
