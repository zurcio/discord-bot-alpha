import discord, time, math
from discord.ext import commands
from core.guards import require_no_lock, set_lock, clear_lock
from core.players import load_profile, save_profile
from systems.raids import (
    load_state, save_state, charge_battery, battery_percent, can_open, open_raid,
    get_status, is_active, maybe_finalize,
    attack_personal, charge_personal_from_materials, get_personal_status,
    charge_mega, convert_to_personal_units, convert_to_mega_units,
    calculate_scrap_total, calculate_material_total, parse_amount,
    get_charge_preview_personal, get_charge_preview_mega,
    MEGA_WEAPON_KEYS, claim_payout, PERSONAL_MAX_CHARGE, MEGA_HOURLY_CONTRIBUTION_LIMIT,
    get_supply_crate_info, get_player_rank
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
        # Track pending confirmations: {user_id: {"type": "charge"/"support", "data": {...}, "expires": timestamp}}
        self.pending_confirmations = {}

    def _cleanup_expired_confirmations(self):
        """Remove confirmations older than 5 minutes."""
        now = int(time.time())
        expired = [uid for uid, data in self.pending_confirmations.items() if data.get("expires", 0) < now]
        for uid in expired:
            del self.pending_confirmations[uid]

    @commands.command(name="raid")
    @require_no_lock()
    async def raid(self, ctx, sub: str = "status", *args):
        sub = (sub or "status").lower()
        uid = str(ctx.author.id)
        
        # Clean up expired confirmations
        self._cleanup_expired_confirmations()
        
        # Check if this is a simple confirmation response (yes/y/no/n)
        if sub in ("yes", "y", "no", "n"):
            confirm = sub in ("yes", "y")
            pending = self.pending_confirmations.get(uid)
            
            if not pending:
                await ctx.send("❌ No pending confirmation found. Confirmations expire after 5 minutes.")
                return
            
            if not confirm:
                del self.pending_confirmations[uid]
                await ctx.send("❌ Cancelled.")
                return
            
            # Process the confirmed action
            action_type = pending.get("type")
            data = pending.get("data", {})
            del self.pending_confirmations[uid]
            
            if action_type == "charge":
                # Execute personal battery charge
                return await self._execute_charge(ctx, uid, data)
            elif action_type == "support":
                # Execute mega weapon support
                return await self._execute_support(ctx, uid, data)
            else:
                await ctx.send("❌ Unknown confirmation type.")
                return

        # status
        if sub in ("s", "status", ""):
            state = load_state()
            # Auto-finalize if needed
            ended = maybe_finalize(state)
            if ended:
                save_state(state)
            st = get_status(state)
            if not st.get("active", False):
                # Check if there's a recent completed raid to show
                hist = state.get("history", [])
                bat = state.get("battery", {})
                cooldown_until = int(bat.get("cooldown_until", 0))
                now = int(time.time())
                
                if hist and cooldown_until > 0 and now < cooldown_until:
                    # Show raid results during cooldown
                    latest = hist[-1]
                    success = latest.get("success", False)
                    title = "🏁 Raid Completed — Victory!" if success else "⏳ Raid Ended"
                    time_left = cooldown_until - now
                    hours = time_left // 3600
                    minutes = (time_left % 3600) // 60
                    
                    embed = discord.Embed(title=title, color=0x2ecc71 if success else 0xe67e22)
                    embed.add_field(name="Boss", value=latest.get("boss_name", "Unknown"), inline=True)
                    embed.add_field(name="Duration", value=f"{latest.get('duration', 0)//3600}h", inline=True)
                    embed.add_field(name="\u200b", value="\u200b", inline=True)
                    
                    # Top 3 contributors
                    top = latest.get("top", [])[:3]
                    if top:
                        top_text = []
                        for i, (pid, dmg) in enumerate(top, 1):
                            claimed_status = "✅" if str(pid) in latest.get("claimed", []) else "⏳"
                            top_text.append(f"{i}. <@{pid}> — {dmg:,} dmg {claimed_status}")
                        embed.add_field(name="🏆 Top 3 Contributors", value="\n".join(top_text), inline=False)
                    
                    # Check if user participated
                    uid = str(ctx.author.id)
                    if uid in latest.get("payouts", {}):
                        rank = get_player_rank(latest, uid)
                        scrap = latest.get("payouts", {}).get(uid, 0)
                        credits = latest.get("credit_payouts", {}).get(uid, 0)
                        crates = sum(latest.get("crate_payouts", {}).get(uid, {}).values())
                        claimed = uid in latest.get("claimed", [])
                        status_emoji = "✅ Claimed" if claimed else "⏳ Pending"
                        embed.add_field(name=f"📊 Your Rank: #{rank}", value=f"Rewards: {scrap:,} Scrap, {credits} Credits, {crates} Crates ({status_emoji})", inline=False)
                    
                    embed.add_field(name="⏰ Next Raid Battery", value=f"Opens in {hours}h {minutes}m", inline=False)
                    embed.set_footer(text="Use !raid claim to collect your rewards!")
                    await ctx.send(embed=embed)
                    return
                
                # Normal battery charging display
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
                personal_status = f"{pct}% (⏳ Cooldown: {_fmt_timeleft(int(time.time())+cd_rem)})"
            else:
                personal_status = f"{pct}% (✅ Ready)"
            embed.add_field(name="🔋 Your Personal Artillery", value=personal_status, inline=False)
            
            # Mega weapon summary with rate limits
            mega_display = []
            mega_container = st.get("mega") or {}
            one_hour_ago = int(time.time()) - 3600
            
            for k in ["plasteel", "circuit", "plasma", "biofiber", "scrap"]:
                if k in mega_container:
                    meta = mega_container[k]
                    prog = int(meta.get("progress", 0)); tgt = int(meta.get("target", 1))
                    pctm = min(100, math.floor(100*prog/tgt))
                    
                    # Check user's rate limit status
                    user_contrib = meta.get("contributors", {}).get(str(uid), {})
                    timestamps = user_contrib.get("timestamps", [])
                    units_last_hour = len([ts for ts in timestamps if ts > one_hour_ago])
                    
                    weapon_status = f"**{MEGA_WEAPON_KEYS.get(k, k)}**: {pctm}%"
                    
                    if units_last_hour >= MEGA_HOURLY_CONTRIBUTION_LIMIT:
                        # Find oldest timestamp to calculate when they can contribute again
                        oldest_recent = min([ts for ts in timestamps if ts > one_hour_ago])
                        time_until_available = oldest_recent + 3600 - int(time.time())
                        weapon_status += f" (⏳ Rate limited: {time_until_available//60}m)"
                    elif units_last_hour > 0:
                        remaining = MEGA_HOURLY_CONTRIBUTION_LIMIT - units_last_hour
                        weapon_status += f" ({remaining}% capacity remaining)"
                    
                    mega_display.append(weapon_status)
            
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
                await ctx.send("Usage: !raid charge <scrap|plasteel|circuit|plasma|biofiber> <amount|k/m/b/half/all>")
                return
            resource = args[0].lower().strip()
            amount_str = args[1].lower().strip()
            
            # Show preview and request confirmation
            if resource not in ("scrap", "plasteel", "circuit", "plasma", "biofiber"):
                await ctx.send("❌ Invalid resource. Use scrap/plasteel/circuit/plasma/biofiber.")
                return
            
            prof = load_profile(uid) or {}
            inv = prof.get("inventory", {}) or {}
            total_scrap = calculate_scrap_total(prof)
            total_materials = calculate_material_total(prof, resource) if resource != "scrap" else 0
            
            # Parse amount
            if resource == "scrap":
                available = int(prof.get("Scrap", 0))
            else:
                available = int(inv.get(resource, 0))
            amount = parse_amount(amount_str, available)
            
            if amount <= 0:
                await ctx.send("❌ Invalid amount.")
                return
            
            if available < amount:
                await ctx.send(f"❌ Not enough {resource}. You have {available:,}.")
                return
            
            # Get current state
            state = load_state()
            if not is_active(state):
                await ctx.send("❌ Raid not active yet. Global battery must reach 100%.")
                return
            
            # Check cooldown
            current_pct, cd = get_personal_status(state, uid)
            if cd > 0:
                await ctx.send(f"⏳ Cooldown active. You can charge again in {_fmt_timeleft(int(time.time())+cd)}.")
                return
            
            # Calculate preview
            preview = get_charge_preview_personal(resource, amount, total_scrap, total_materials, current_pct)
            
            if preview["units"] <= 0:
                await ctx.send(f"❌ Amount too small to convert. Minimum needed: **{preview['cost_per_unit']:,} {resource}** for 1% charge.")
                return
            
            # Build confirmation message
            lines = [f"🔋 **Personal Battery Charge Preview**"]
            lines.append(f"Current Charge: **{current_pct}%**")
            lines.append(f"Contributing: **{preview['capped_amount']:,} {resource}**")
            lines.append(f"Charge Gain: **+{preview['percent_gain']}%** ({preview['units']} units)")
            lines.append(f"Final Charge: **{preview['final_percent']}%**")
            lines.append(f"Cost per 1%: **{preview['cost_per_unit']:,} {resource}**")
            
            if preview["was_capped"]:
                lines.append(f"⚠️ Contribution capped at {PERSONAL_MAX_CHARGE}% max charge.")
            
            if preview["will_overcharge"]:
                overcharge_pct = preview['final_percent'] - 100
                overcharge_factor = overcharge_pct / 100.0
                cooldown_min = int(60 * (1 + 0.5 * overcharge_factor))
                lines.append(f"⚡ **Overcharge:** Attack cooldown will be **{cooldown_min} minutes** (base 60min + {int(overcharge_factor*50)}% penalty).")
            
            # Store pending confirmation
            self.pending_confirmations[uid] = {
                "type": "charge",
                "data": {
                    "resource": resource,
                    "amount": amount,
                    "capped_amount": preview["capped_amount"],
                    "units": preview["units"]
                },
                "expires": int(time.time()) + 300  # 5 minutes
            }
            
            lines.append(f"\n💡 Reply with `!raid yes` or `!raid y` to confirm, `!raid no` or `!raid n` to cancel.")
            lines.append(f"⏱️ *Confirmation expires in 5 minutes.*")
            await ctx.send("\n".join(lines))
            return

        # support mega weapon charge
        if sub in ("sup", "support"):
            if len(args) < 2:
                await ctx.send("Usage: !raid support <scrap|plasteel|circuit|plasma|biofiber> <amount|k/m/b/half/all>")
                return
            key = args[0].lower().strip()
            amount_str = args[1].lower().strip()
            
            # Show preview and request confirmation
            if key not in MEGA_WEAPON_KEYS:
                await ctx.send("❌ Invalid mega weapon. Use: " + ", ".join(MEGA_WEAPON_KEYS.keys()))
                return
            
            prof = load_profile(uid) or {}
            inv = prof.get("inventory", {}) or {}
            total_scrap = calculate_scrap_total(prof)
            total_materials = calculate_material_total(prof, key) if key != "scrap" else 0
            
            # Parse amount
            if key == "scrap":
                available = int(prof.get("Scrap", 0))
            else:
                available = int(inv.get(key, 0))
            amount = parse_amount(amount_str, available)
            
            if amount <= 0:
                await ctx.send("❌ Invalid amount.")
                return
            
            if available < amount:
                await ctx.send(f"❌ Not enough {key}. You have {available:,}.")
                return
            
            # Get current state
            state = load_state()
            if not is_active(state):
                await ctx.send("❌ Raid not active yet.")
                return
            
            # Get weapon status
            mega_container = state.get("active", {}).get("mega", {})
            weapon_entry = mega_container.get(key, {})
            current_pct = int(min(100, math.floor(100.0 * weapon_entry.get("progress", 0) / max(1, weapon_entry.get("target", 100)))))
            
            # Calculate units contributed in last hour for rate limiting
            user_contrib = weapon_entry.get("contributors", {}).get(str(uid), {})
            timestamps = user_contrib.get("timestamps", [])
            one_hour_ago = int(time.time()) - 3600
            units_last_hour = len([ts for ts in timestamps if ts > one_hour_ago])
            
            # Calculate preview
            preview = get_charge_preview_mega(key, amount, total_scrap, total_materials, current_pct, units_last_hour)
            
            if preview["units"] <= 0:
                if preview["rate_limited"]:
                    await ctx.send(f"⏱️ **Rate Limit Reached**\nMax {MEGA_HOURLY_CONTRIBUTION_LIMIT}% per hour. Available capacity: **{preview['available_capacity']} units**.\nTry again later or contribute less.")
                else:
                    await ctx.send(f"❌ Amount too small to convert. Minimum needed: **{preview['cost_per_unit']:,} {key}** for 1% charge.")
                return
            
            # Build confirmation message
            lines = [f"🛠 **{MEGA_WEAPON_KEYS[key]} Charge Preview**"]
            lines.append(f"Current Charge: **{current_pct}%**")
            lines.append(f"Contributing: **{preview['capped_amount']:,} {key}**")
            lines.append(f"Charge Gain: **+{preview['percent_gain']}%** ({preview['units']} units)")
            lines.append(f"Final Charge: **{current_pct + preview['percent_gain']}%**")
            lines.append(f"Cost per 1%: **{preview['cost_per_unit']:,} {key}**")
            lines.append(f"Rate Limit: **{units_last_hour + preview['units']}/{MEGA_HOURLY_CONTRIBUTION_LIMIT}** units per hour")
            
            if preview["rate_limited"]:
                lines.append(f"⚠️ **Capped to 10% per hour limit.** You can only contribute {preview['available_capacity']} more units this hour.")
            
            if preview["will_fire"]:
                lines.append(f"💥 **Weapon will FIRE** at the boss (10% max HP damage)!")
            
            # Store pending confirmation
            self.pending_confirmations[uid] = {
                "type": "support",
                "data": {
                    "key": key,
                    "amount": amount,
                    "capped_amount": preview["capped_amount"],
                    "units": preview["units"]
                },
                "expires": int(time.time()) + 300  # 5 minutes
            }
            
            lines.append(f"\n💡 Reply with `!raid yes` or `!raid y` to confirm, `!raid no` or `!raid n` to cancel.")
            lines.append(f"⏱️ *Confirmation expires in 5 minutes.*")
            await ctx.send("\n".join(lines))
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
            scrap_amt, crate_rewards, credits_amt, summary, player_rank = claim_payout(state, uid)
            save_state(state)
            if not summary:
                await ctx.send("❌ No completed raid to claim from.")
                return
            if scrap_amt <= 0 and not crate_rewards and credits_amt <= 0:
                if str(uid) in summary.get("claimed", []):
                    await ctx.send("✅ Rewards already claimed for this raid.")
                else:
                    await ctx.send("❌ You earned no rewards this raid.")
                return
            
            # Build reward display embed
            embed = discord.Embed(
                title="🎉 Raid Rewards Claimed",
                description=f"**{summary.get('boss_name', 'Raid')}** — Rank #{player_rank}",
                color=0x2ecc71
            )
            
            # Show top 3 rewards
            top = summary.get("top", [])[:3]
            if top:
                top_text = []
                for i, (pid, dmg) in enumerate(top, 1):
                    top_scrap = summary.get("payouts", {}).get(str(pid), 0)
                    top_crates = summary.get("crate_payouts", {}).get(str(pid), {})
                    top_credits = summary.get("credit_payouts", {}).get(str(pid), 0)
                    total_crates = sum(top_crates.values()) if top_crates else 0
                    top_text.append(f"**#{i}** <@{pid}>: {top_scrap:,} Scrap, {top_credits} Credits, {total_crates} Crates")
                embed.add_field(name="🏆 Top 3 Contributors", value="\n".join(top_text), inline=False)
            
            # Apply rewards to profile
            prof = load_profile(uid) or {}
            
            # Apply scrap
            if scrap_amt > 0:
                prof["Scrap"] = int(prof.get("Scrap", 0)) + scrap_amt
                embed.add_field(name="💰 Scrap", value=f"+{scrap_amt:,}", inline=True)
            
            # Apply credits
            if credits_amt > 0:
                prof["Credits"] = int(prof.get("Credits", 0)) + credits_amt
                embed.add_field(name="💎 Credits", value=f"+{credits_amt}", inline=True)
            
            # Apply supply crates with detailed display
            if crate_rewards:
                inv = prof.get("inventory", {})
                
                # Sort crates by rarity (reverse order for display)
                crate_order = ["305", "304", "303", "302", "301", "300"]  # Solar to Common
                sorted_crates = [(cid, qty) for cid in crate_order if cid in crate_rewards for qty in [crate_rewards[cid]]]
                
                crate_lines = []
                for item_id, qty in sorted_crates:
                    inv[item_id] = int(inv.get(item_id, 0)) + qty
                    name, emoji = get_supply_crate_info(item_id)
                    crate_lines.append(f"{emoji} **{qty}x** {name}")
                
                prof["inventory"] = inv
                embed.add_field(name="📦 Supply Crates", value="\n".join(crate_lines), inline=False)
            
            save_profile(uid, prof)
            
            embed.set_footer(text=f"Raid ID: {summary.get('raid_id')}")
            await ctx.send(embed=embed)
            return

        await ctx.send("Usage: !raid status | !raid charge <res> <amt> | !raid attack | !raid support <res> <amt> | !raid leaderboard | !raid claim")

    async def _payout_summary(self, ctx, summary: dict):
        title = "🏁 Raid Finished — Victory!" if summary.get("success") else "⏳ Raid Ended"
        
        embed = discord.Embed(
            title=title,
            description=f"**{summary.get('boss_name')}** • Duration: {int(summary.get('duration',0))//3600}h",
            color=0x2ecc71 if summary.get("success") else 0xe67e22
        )
        
        payouts = summary.get("payouts", {})
        crate_payouts = summary.get("crate_payouts", {})
        
        if payouts:
            display = sorted(payouts.items(), key=lambda kv: -kv[1])[:10]
            scrap_text = []
            for rank, (uid, amt) in enumerate(display, 1):
                total_crates = sum(crate_payouts.get(uid, {}).values())
                scrap_text.append(f"**#{rank}** <@{uid}>: {amt:,} Scrap, {total_crates} Crates")
            embed.add_field(name="🏆 Top 10 Contributors", value="\n".join(scrap_text), inline=False)
        
        embed.set_footer(text="Use !raid claim to collect your rewards!")
        await ctx.send(embed=embed)

    async def _execute_charge(self, ctx, uid: str, data: dict):
        """Execute a confirmed personal battery charge."""
        resource = data["resource"]
        amount = data["amount"]
        capped_amount = data["capped_amount"]
        units = data["units"]
        
        set_lock(uid, "raid_charge", allowed=set(), note="raid charge")
        try:
            prof = load_profile(uid) or {}
            inv = prof.get("inventory", {}) or {}
            
            # Deduct resources
            if resource == "scrap":
                prof["Scrap"] = int(prof.get("Scrap", 0)) - capped_amount
            else:
                inv[resource] = int(inv.get(resource, 0)) - capped_amount
                if inv[resource] <= 0:
                    inv.pop(resource, None)
                prof["inventory"] = inv
            
            # Charge battery
            state = load_state()
            if not is_active(state):
                # Refund
                if resource == "scrap":
                    prof["Scrap"] = int(prof.get("Scrap", 0)) + capped_amount
                else:
                    inv[resource] = int(inv.get(resource, 0)) + capped_amount
                    prof["inventory"] = inv
                save_profile(uid, prof)
                await ctx.send("❌ Raid is no longer active.")
                return
            
            current_pct, cd = get_personal_status(state, uid)
            if cd > 0:
                # Refund
                if resource == "scrap":
                    prof["Scrap"] = int(prof.get("Scrap", 0)) + capped_amount
                else:
                    inv[resource] = int(inv.get(resource, 0)) + capped_amount
                    prof["inventory"] = inv
                save_profile(uid, prof)
                await ctx.send(f"⏳ Cooldown active. You can charge again in {_fmt_timeleft(int(time.time())+cd)}.")
                return
            
            pct_after, _, actual_units = charge_personal_from_materials(state, uid, units)
            save_state(state)
            save_profile(uid, prof)
            
            # Feedback with overcharge indication
            cooldown_msg = ""
            if pct_after > 100:
                # Calculate overcharge cooldown
                overcharge_factor = (pct_after - 100) / 100.0
                cooldown_sec = int(3600 * (1 + 0.5 * overcharge_factor))
                cooldown_msg = f"\n⚡ **Overcharged!** Attack cooldown will be {cooldown_sec//60} minutes (base 60min + overcharge penalty)."
            
            await ctx.send(f"✅ Charged **{actual_units}%** ({capped_amount:,} {resource}). Personal Battery: **{current_pct}%** → **{pct_after}%**{cooldown_msg}")
        finally:
            clear_lock(uid)

    async def _execute_support(self, ctx, uid: str, data: dict):
        """Execute a confirmed mega weapon support."""
        key = data["key"]
        amount = data["amount"]
        capped_amount = data["capped_amount"]
        units = data["units"]
        
        set_lock(uid, "raid_support", allowed=set(), note="raid support")
        try:
            prof = load_profile(uid) or {}
            inv = prof.get("inventory", {}) or {}
            
            # Deduct resources
            if key == "scrap":
                prof["Scrap"] = int(prof.get("Scrap", 0)) - capped_amount
            else:
                inv[key] = int(inv.get(key, 0)) - capped_amount
                if inv[key] <= 0:
                    inv.pop(key, None)
                prof["inventory"] = inv
            
            # Charge weapon
            state = load_state()
            if not is_active(state):
                # Refund
                if key == "scrap":
                    prof["Scrap"] = int(prof.get("Scrap", 0)) + capped_amount
                else:
                    inv[key] = int(inv.get(key, 0)) + capped_amount
                    prof["inventory"] = inv
                save_profile(uid, prof)
                await ctx.send("❌ Raid is no longer active.")
                return
            
            # Get current %
            mega_container = state.get("active", {}).get("mega", {})
            weapon_entry = mega_container.get(key, {})
            current_pct = int(min(100, math.floor(100.0 * weapon_entry.get("progress", 0) / max(1, weapon_entry.get("target", 100)))))
            
            pct_after, fired, dmg, rate_msg, actual_units = charge_mega(state, uid, key, units)
            save_state(state)
            save_profile(uid, prof)
            
            if fired:
                boss_name = state.get("active", {}).get("boss_name", "the boss")
                await ctx.send(f"💥 {ctx.author.mention} charged the **{MEGA_WEAPON_KEYS[key]}**! It fires at **{boss_name}** for **{dmg:,} damage**!")
                # Check raid end
                state = load_state()
                ended = maybe_finalize(state)
                if ended:
                    save_state(state)
                    await self._payout_summary(ctx, ended)
                else:
                    save_state(state)
            else:
                await ctx.send(f"✅ Charged **{actual_units}%** ({capped_amount:,} {key}). {MEGA_WEAPON_KEYS[key]}: **{current_pct}%** → **{pct_after}%**")
        finally:
            clear_lock(uid)

async def setup(bot):
    await bot.add_cog(Raid(bot))
