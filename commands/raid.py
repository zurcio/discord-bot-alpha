import discord, time, math
from discord.ext import commands
from core.guards import require_no_lock, set_lock, clear_lock
from core.players import load_profile, save_profile
from systems.raids import (
    load_state, save_state, charge_battery, battery_percent, can_open, open_raid,
    get_status, is_active, maybe_finalize,
    attack_personal, charge_personal_from_materials, get_personal_status,
    charge_mega, convert_to_personal_units, convert_to_mega_units,
    calculate_scrap_total, MEGA_WEAPON_KEYS, claim_payout,
    PERSONAL_SCRAP_PERCENT_PER_UNIT, PERSONAL_MATERIALS_PER_UNIT,
    MEGA_SCRAP_PERCENT_PER_UNIT, MEGA_MATERIALS_PER_UNIT
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
                embed = discord.Embed(title="⚡ Raid Battery Charging", color=0x3498db)
                embed.add_field(name="Progress", value=f"{p}%", inline=False)
                embed.add_field(name="Status", value="Fill to 100% to auto-open a raid!", inline=False)
                embed.add_field(name="How to Charge", value="Play the game! Actions like scan, work, research, and explore charge the battery.", inline=False)
                await ctx.send(embed=embed)
                return
            
            # Active raid display
            hp = st["hp"]; hp_max = st["hp_max"]
            hp_pct = int(100 * hp / max(1, hp_max))
            tl = _fmt_timeleft(st["ends_at"])
            
            embed = discord.Embed(title=f"🧟 {st['boss_name']}", color=0xe74c3c)
            embed.add_field(name="Boss HP", value=f"{hp:,} / {hp_max:,} ({hp_pct}%)", inline=True)
            embed.add_field(name="Time Remaining", value=tl, inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)  # spacer
            
            # Personal battery status
            pct, cd_rem = get_personal_status(state, uid)
            if cd_rem > 0:
                personal_status = f"{pct}% (⏳ {cd_rem//60}m cooldown)"
            else:
                personal_status = f"{pct}%"
            embed.add_field(name="🔋 Your Personal Artillery", value=personal_status, inline=False)
            
            # Mega weapon summary
            mega_display = []
            for k in ["plasteel", "circuit", "plasma", "biofiber", "scrap"]:
                if k in (st.get("mega") or {}):
                    meta = st["mega"][k]
                    prog = int(meta.get("progress", 0)); tgt = int(meta.get("target", 1))
                    pctm = min(100, math.floor(100*prog/tgt))
                    mega_display.append(f"**{MEGA_WEAPON_KEYS.get(k, k)}**: {pctm}%")
            
            if mega_display:
                embed.add_field(name="🛠 Mega Weapons", value="\n".join(mega_display), inline=False)
            
            # Top contributors
            top = st.get("top5", [])
            if top:
                top_text = []
                for i, (pid, dmg) in enumerate(top, 1):
                    top_text.append(f"{i}. <@{pid}> — {dmg:,} dmg")
                embed.add_field(name="🏆 Top Contributors", value="\n".join(top_text), inline=False)
            
            embed.set_footer(text="Use !raid charge/attack/support to participate | !raid claim to collect rewards after raid ends")
            await ctx.send(embed=embed)
            return

        # attack (personal artillery)
        if sub in ("a", "attack"):
            # Check if this is confirmation (second call)
            if len(args) >= 1 and args[0].lower() in ("y", "yes", "confirm"):
                # Execute actual attack
                set_lock(uid, "raid_attack", allowed=set(), note="raid attack")
                try:
                    state = load_state()
                    ended = maybe_finalize(state)
                    if ended:
                        save_state(state)
                        await ctx.send("Raid has ended. Try again later.")
                        return
                    if not is_active(state):
                        await ctx.send("No active raid. Charge the global battery to open one.")
                        return
                    dmg, hp_after, pct_used, cd_block = attack_personal(state, uid)
                    save_state(state)
                    if cd_block > 0:
                        await ctx.send(f"⏳ Cooldown active. You can attack again in {_fmt_timeleft(int(time.time())+cd_block)}.")
                        return
                    if dmg <= 0:
                        await ctx.send(f"{ctx.author.mention} Battery {pct_used}% — insufficient charge to fire.")
                        return
                    await ctx.send(f"🔫 {ctx.author.mention} fired at {pct_used}% charge for {dmg:,} dmg. Boss HP: {hp_after:,}.")
                    # Check end
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
            
            # Show preview and ask for confirmation
            state = load_state()
            ended = maybe_finalize(state)
            if ended:
                save_state(state)
                await ctx.send("Raid has ended. Try again later.")
                return
            if not is_active(state):
                await ctx.send("No active raid. Charge the global battery to open one.")
                return
            
            pct, cd_rem = get_personal_status(state, uid)
            if cd_rem > 0:
                await ctx.send(f"⏳ Cooldown active. You can charge again in {_fmt_timeleft(int(time.time())+cd_rem)}.")
                return
            if pct <= 0:
                await ctx.send(f"{ctx.author.mention} Your personal battery is empty (0%). Use !raid charge to fill it first.")
                return
            
            # Show confirmation prompt
            await ctx.send(f"🔫 {ctx.author.mention} Your personal battery is at **{pct}%** charge.\n"
                          f"Fire artillery? This will consume all charge and trigger a 1-hour cooldown.\n"
                          f"Reply with `!raid attack yes` to confirm.")
            return

        # charge personal battery
        if sub in ("c", "charge"):
            if len(args) < 2:
                await ctx.send("Usage: !raid charge <scrap|plasteel|circuit|plasma|biofiber> <amount>")
                return
            resource = args[0].lower().strip()
            try:
                amount = max(1, int(args[1]))
            except Exception:
                await ctx.send("Invalid amount.")
                return
            if resource not in ("scrap", "plasteel", "circuit", "plasma", "biofiber"):
                await ctx.send("Invalid resource. Use scrap/plasteel/circuit/plasma/biofiber.")
                return
            prof = load_profile(uid) or {}
            inv = prof.get("inventory", {}) or {}
            total_scrap = calculate_scrap_total(prof)
            # Check availability & deduct
            if resource == "scrap":
                have = int(prof.get("Scrap", 0))
                if have < amount:
                    await ctx.send("Not enough Scrap.")
                    return
                prof["Scrap"] = have - amount
            else:
                have = int(inv.get(resource, 0))
                if have < amount:
                    await ctx.send(f"Not enough {resource}.")
                    return
                inv[resource] = have - amount
                if inv[resource] <= 0:
                    inv.pop(resource, None)
                prof["inventory"] = inv
            units = convert_to_personal_units(resource, amount, total_scrap)
            
            # Check if conversion yielded any units
            if units <= 0:
                # Refund - amount too small to convert
                if resource == "scrap":
                    prof["Scrap"] = int(prof.get("Scrap", 0)) + amount
                else:
                    inv[resource] = int(inv.get(resource, 0)) + amount
                    prof["inventory"] = inv
                save_profile(uid, prof)
                min_needed = max(1, int(math.ceil(total_scrap * PERSONAL_SCRAP_PERCENT_PER_UNIT / 100))) if resource == "scrap" else PERSONAL_MATERIALS_PER_UNIT
                await ctx.send(f"❌ Amount too small to convert to charge units. Minimum needed: {min_needed:,} {resource}.")
                return
            
            set_lock(uid, "raid_charge", allowed=set(), note="raid charge")
            try:
                state = load_state()
                if not is_active(state):
                    await ctx.send("Raid not active yet. Global battery must reach 100%.")
                    # refund
                    if resource == "scrap":
                        prof["Scrap"] = int(prof.get("Scrap", 0)) + amount
                    else:
                        inv[resource] = int(inv.get(resource, 0)) + amount
                        prof["inventory"] = inv
                    save_profile(uid, prof)
                    return
                pct_after, cd = charge_personal_from_materials(state, uid, units)
                if cd > 0:
                    await ctx.send(f"⏳ Cooldown active. You can charge again in {_fmt_timeleft(int(time.time())+cd)}.")
                    # refund
                    if resource == "scrap":
                        prof["Scrap"] = int(prof.get("Scrap", 0)) + amount
                    else:
                        inv[resource] = int(inv.get(resource, 0)) + amount
                        prof["inventory"] = inv
                    save_profile(uid, prof)
                    return
                save_state(state)
                save_profile(uid, prof)
                await ctx.send(f"🔋 Charged {units} units. Personal Battery now {pct_after}%.")
            finally:
                clear_lock(uid)
            return

        # support mega weapon charge (renamed behavior)
        if sub in ("sup", "support"):
            if len(args) < 2:
                await ctx.send("Usage: !raid support <scrap|plasteel|circuit|plasma|biofiber> <amount>")
                return
            key = args[0].lower().strip()
            try:
                amount = max(1, int(args[1]))
            except Exception:
                await ctx.send("Invalid amount.")
                return
            if key not in MEGA_WEAPON_KEYS:
                await ctx.send("Invalid mega weapon resource key.")
                return
            prof = load_profile(uid) or {}
            inv = prof.get("inventory", {}) or {}
            total_scrap = calculate_scrap_total(prof)
            if key == "scrap":
                have = int(prof.get("Scrap", 0))
                if have < amount:
                    await ctx.send("Not enough Scrap.")
                    return
                prof["Scrap"] = have - amount
            else:
                have = int(inv.get(key, 0))
                if have < amount:
                    await ctx.send(f"Not enough {key}.")
                    return
                inv[key] = have - amount
                if inv[key] <= 0:
                    inv.pop(key, None)
                prof["inventory"] = inv
            units = convert_to_mega_units(key, amount, total_scrap)
            
            # Check if conversion yielded any units
            if units <= 0:
                # Refund - amount too small to convert
                if key == "scrap":
                    prof["Scrap"] = int(prof.get("Scrap", 0)) + amount
                else:
                    inv[key] = int(inv.get(key, 0)) + amount
                    prof["inventory"] = inv
                save_profile(uid, prof)
                min_needed = max(1, int(math.ceil(total_scrap * MEGA_SCRAP_PERCENT_PER_UNIT / 100))) if key == "scrap" else MEGA_MATERIALS_PER_UNIT
                await ctx.send(f"❌ Amount too small to convert to charge units. Minimum needed: {min_needed:,} {key}.")
                return
            
            set_lock(uid, "raid_support", allowed=set(), note="raid support")
            try:
                state = load_state()
                if not is_active(state):
                    await ctx.send("Raid not active yet.")
                    # refund
                    if key == "scrap":
                        prof["Scrap"] = int(prof.get("Scrap", 0)) + amount
                    else:
                        inv[key] = int(inv.get(key, 0)) + amount
                        prof["inventory"] = inv
                    save_profile(uid, prof)
                    return
                pct_after, fired, dmg, cd = charge_mega(state, uid, key, units)
                if cd > 0:
                    await ctx.send(f"⏳ Cooldown active. You can charge {MEGA_WEAPON_KEYS[key]} again in {_fmt_timeleft(int(time.time())+cd)}.")
                    # refund
                    if key == "scrap":
                        prof["Scrap"] = int(prof.get("Scrap", 0)) + amount
                    else:
                        inv[key] = int(inv.get(key, 0)) + amount
                        prof["inventory"] = inv
                    save_profile(uid, prof)
                    return
                save_state(state)
                save_profile(uid, prof)
                if fired:
                    boss_name = state.get("active", {}).get("boss_name", "the boss")
                    await ctx.send(f"💥 {ctx.author.mention} charged the **{MEGA_WEAPON_KEYS[key]}**! It fires at **{boss_name}** for {dmg:,} damage!")
                    # Check raid end
                    state = load_state()
                    ended = maybe_finalize(state)
                    if ended:
                        save_state(state)
                        await self._payout_summary(ctx, ended)
                    else:
                        save_state(state)
                else:
                    await ctx.send(f"🛠 Charged {units} units. {MEGA_WEAPON_KEYS[key]} now {pct_after}%.")
            finally:
                clear_lock(uid)
            return

        # Manual open retained for owner (fallback / testing)
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
            await ctx.send("⚔️ Raid opened manually. Use !raid attack / charge / support.")
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

        # claim rewards
        if sub in ("claim", "cl"):
            state = load_state()
            amt, summary = claim_payout(state, uid)
            save_state(state)
            if not summary:
                await ctx.send("No completed raid to claim from.")
                return
            if amt <= 0:
                if str(uid) in summary.get("claimed", []):
                    await ctx.send("Rewards already claimed.")
                else:
                    await ctx.send("You earned no rewards this raid.")
                return
            # apply payout
            prof = load_profile(uid) or {}
            prof["Scrap"] = int(prof.get("Scrap", 0)) + amt
            save_profile(uid, prof)
            await ctx.send(f"✅ Claimed {amt:,} Scrap from raid {summary.get('raid_id')}.")
            return

        await ctx.send("Usage: !raid status | !raid charge <res> <amt> | !raid attack | !raid support <res> <amt> | !raid leaderboard | !raid claim")

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
            # Payouts now claimed via !raid claim (do not auto apply here)
        await ctx.send("\n".join(lines))

async def setup(bot):
    await bot.add_cog(Raid(bot))
