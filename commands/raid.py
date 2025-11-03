import discord, time
from discord.ext import commands
from core.guards import require_no_lock, set_lock, clear_lock
from core.players import load_profile, save_profile
from systems.ship_sys import ensure_ship
from core.sector import ensure_sector, sector_bonus_multiplier
from systems.raids import (
    load_state, save_state, charge_battery, battery_percent, can_open, open_raid,
    get_status, is_active, attack, add_support, maybe_finalize,
    SUPPORT_COST_PER_MIN, SUPPORT_MAX_MINUTES_STACK
)

def _fmt_timeleft(ts: int) -> str:
    rem = max(0, ts - int(time.time()))
    h = rem // 3600
    m = (rem % 3600) // 60
    s = rem % 60
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

class Raid(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="raid")
    @require_no_lock()
    async def raid(self, ctx, sub: str = "status", *args):
        sub = (sub or "status").lower()
        uid = str(ctx.author.id)

        # status
        if sub in ("s", "status", ""):
            state = load_state()
            # Auto-finalize if needed
            ended = maybe_finalize(state)
            if ended:
                save_state(state)
            st = get_status(state)
            if not st.get("active", False):
                p = st["battery_percent"]
                await ctx.send(f"⚡ Raid Battery: {p}% — charge it by playing (scan/work/research/explore).")
                return
            hp = st["hp"]; hp_max = st["hp_max"]
            tl = _fmt_timeleft(st["ends_at"])
            lines = [f"🧟 Boss: {st['boss_name']}  HP: {hp:,}/{hp_max:,}  ⏳ {tl}", f"Group Buff: x{st['group_buff_mult']:.2f}"]
            top = st.get("top5", [])
            if top:
                lines.append("Top Contributors:")
                for i, (pid, dmg) in enumerate(top, 1):
                    tag = f"<@{pid}>"
                    lines.append(f"{i}. {tag} — {dmg:,} dmg")
            await ctx.send("\n".join(lines))
            return

        # attack
        if sub in ("a", "attack"):
            if len(args) < 1:
                await ctx.send(f"{ctx.author.mention} usage: !raid attack <oxygen>")
                return
            try:
                oxy = max(1, int(args[0]))
            except Exception:
                await ctx.send("Invalid oxygen amount.")
                return

            # Load player, ship, sector
            prof = load_profile(uid) or {}
            ensure_ship(prof)
            ship = prof.get("ship", {})
            tier = int(ship.get("tier", 1)); level = int(ship.get("level", 1))
            sec = ensure_sector(prof)
            sec_mult = float(sector_bonus_multiplier(sec))

            # Optional: consume Oxygen if tracked on profile
            avail_oxy = int(prof.get("Oxygen", 0))
            if avail_oxy > 0:
                consume = min(avail_oxy, oxy)
                prof["Oxygen"] = avail_oxy - consume
                save_profile(uid, prof)
                # If not enough oxygen, still proceed with what they had
                oxy = consume if consume > 0 else oxy

            set_lock(uid, "raid_attack", allowed=set(), note="raid attack")
            try:
                state = load_state()
                # Auto-finalize if ended
                ended = maybe_finalize(state)
                if ended:
                    save_state(state)
                    await ctx.send(f"Raid has ended. Try again later.")
                    return
                if not is_active(state):
                    await ctx.send("No active raid. Charge the battery with gameplay to open one.")
                    return
                dmg, hp_after, gmult = attack(state, uid, tier, level, sec_mult, oxy)
                save_state(state)
                if dmg <= 0:
                    await ctx.send(f"{ctx.author.mention} your attack had no effect.")
                    return
                await ctx.send(f"🗡️ {ctx.author.mention} dealt {dmg:,} damage (Group x{gmult:.2f}). Boss HP: {hp_after:,}.")
                # Check end after damage
                state = load_state()
                ended = maybe_finalize(state)
                if ended:
                    save_state(state)
                    await self._payout_summary(ctx, ended)
                else:
                    save_state(state)
            finally:
                clear_lock(uid)
            return

        # support
        if sub in ("sup", "support"):
            if len(args) < 1:
                await ctx.send(f"{ctx.author.mention} usage: !raid support <minutes 1..{SUPPORT_MAX_MINUTES_STACK}>")
                return
            try:
                mins = max(1, min(SUPPORT_MAX_MINUTES_STACK, int(args[0])))
            except Exception:
                await ctx.send("Invalid minutes.")
                return

            prof = load_profile(uid) or {}
            cost = int(SUPPORT_COST_PER_MIN * mins)
            scrap = int(prof.get("Scrap", 0))
            if scrap < cost:
                await ctx.send(f"{ctx.author.mention} need {cost} Scrap to fund support for {mins} min (you have {scrap}).")
                return

            set_lock(uid, "raid_support", allowed=set(), note="raid support")
            try:
                state = load_state()
                if not is_active(state):
                    await ctx.send("No active raid.")
                    return
                prof["Scrap"] = scrap - cost
                save_profile(uid, prof)

                add_mult, exp = add_support(state, uid, mins, note=f"Supplied fighters for {mins} min")
                save_state(state)
                if add_mult <= 0.0:
                    await ctx.send("Support failed to apply.")
                    return
                until = _fmt_timeleft(exp)
                await ctx.send(f"📦 {ctx.author.mention} supplied fighters: +{add_mult*100:.0f}% group damage for ~{until}.")
            finally:
                clear_lock(uid)
            return

        # owner-only open (force when battery full)
        if sub in ("o", "open"):
            if not await self.bot.is_owner(ctx.author):
                await ctx.send("Owner only.")
                return
            state = load_state()
            if not can_open(state):
                await ctx.send("Battery not full yet.")
                return
            ok = open_raid(state, boss_name="World Eater")
            save_state(state)
            await ctx.send("⚔️ Raid opened for 48h. Use !raid attack and !raid support.")
            return

        # leaderboard (active)
        if sub in ("lb", "leaderboard"):
            state = load_state()
            st = get_status(state)
            if not st.get("active", False):
                await ctx.send("No active raid.")
                return
            top = st.get("top5", [])
            if not top:
                await ctx.send("No contributions yet.")
                return
            lines = ["🏆 Raid Leaderboard (Top 5):"]
            for i, (pid, dmg) in enumerate(top, 1):
                lines.append(f"{i}. <@{pid}> — {dmg:,} dmg")
            await ctx.send("\n".join(lines))
            return

        await ctx.send("Usage: !raid status | !raid attack <oxygen> | !raid support <minutes> | !raid leaderboard")

    async def _payout_summary(self, ctx, summary: dict):
        title = "🏁 Raid Finished — Victory!" if summary.get("success") else "⏳ Raid Ended"
        lines = [
            f"{title}",
            f"Boss: {summary.get('boss_name')} • Duration: {int(summary.get('duration',0))//3600}h",
        ]
        payouts = summary.get("payouts", {})
        if payouts:
            lines.append("Rewards (Scrap):")
            display = sorted(payouts.items(), key=lambda kv: -kv[1])[:10]
            for uid, amt in display:
                lines.append(f"• <@{uid}> +{amt:,} Scrap")
            # Apply payouts to profiles
            for uid, amt in payouts.items():
                prof = load_profile(str(uid)) or {}
                prof["Scrap"] = int(prof.get("Scrap", 0)) + int(amt)
                save_profile(str(uid), prof)
        await ctx.send("\n".join(lines))

async def setup(bot):
    await bot.add_cog(Raid(bot))
