import random
import discord
import asyncio  # NEW
from discord.ext import commands
from core.decorators import requires_profile
from core.players import save_profile, load_profile
import time
from datetime import timedelta
from core.cooldowns import check_and_set_cooldown, set_cooldown, get_cooldown, command_cooldowns
from core.skills_hooks import soldier_effects
from systems.ship_sys import (
    ensure_ship, grant_starter_ship, has_ship, mk_name, SHIP_TYPES,
    derive_ship_effects, upgrade_cost_for_next_level,
    can_tier, roll_tier_up, max_attempts_for_tier, MAX_TIER, MAX_LEVEL,
)

class Ship(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ship")
    @requires_profile()
    async def ship(self, ctx, subcmd: str = None, *, rest: str = ""):
        """
        !ship → show your ship
        !ship upgrade → level up (costs Scrap)
        !ship refit [solo|@ally] → attempt tier-up (solo has lower success). At MK10, refit rerolls type only.
        """
        player = ctx.player
        ensure_ship(player)

        sub = (subcmd or "").lower()
        if sub in ("", "show", "info"):
            await self._show(ctx, player)
            return
        if sub == "upgrade":
            await self._upgrade(ctx, player)
            return
        if sub in ("refit", "tier", "tierup"):
            await self._refit(ctx, player, rest)
            return

        await ctx.send(f"{ctx.author.mention}, usage: `!ship`, `!ship upgrade`, `!ship refit [@ally] [type]`")

    async def _show(self, ctx, player: dict):
        ensure_ship(player)
        ship = player["ship"]
        if not ship.get("owned"):
            await ctx.send(
                f"{ctx.author.mention}, you don’t own a ship yet. Buy a Starter Ship from the shop with `!buy starter ship`."
            )
            return

        tier = ship.get("tier", 1)
        level = ship.get("level", 1)
        stype = ship.get("type") or "untyped"
        effects = derive_ship_effects(player)
        type_boost = effects["type_boost"]
        tb_text = f"{type_boost['stat']} +{type_boost['value']*100:.2f}%" if type_boost["stat"] else "None"

        # Soldier perks → effective max level and cost reduction
        s_eff = soldier_effects(player)
        eff_max_level = MAX_LEVEL + int(s_eff.get("ship_max_level_bonus", 0))
        cost_reduction = float(s_eff.get("ship_upgrade_cost_reduction", 0.0))

        embed = discord.Embed(
            title=f"{ctx.author.name}'s Ship",
            description=f"Tier: {mk_name(tier).upper()} • Level: {level}/{eff_max_level} • Type: {stype.title() if stype else 'None'}",
            color=discord.Color.dark_blue(),
        )
        embed.add_field(name="Core Modules", value=(
            f"• Rewards Mult: x{effects['rewards_mult']:.2f} (daily/weekly)\n"
            f"• Supply Crate Chance Mult: x{effects['supply_crate_mult']:.2f} (mk4+)\n"
            f"• Drop Chance Mult: x{effects['drop_chance_mult']:.2f} (mk8+)\n"
            f"• Crew Chance Mult: x{effects['crew_chance_mult']:.2f} (mk7+)\n"
            f"• Life Support (mk5+): {'✅' if effects['life_support'] else '❌'}\n"
            f"• Keycard Override (mk6+): {'✅' if effects['keycard_override'] else '❌'}\n"
            f"• Double Drops & Supply Crates (mk10): {'✅' if effects['double_drops'] else '❌'}"
        ), inline=False)
        embed.add_field(name="Type Boost", value=tb_text, inline=False)

        # Legacy arg kept; we apply Soldier reduction here
        ship_skill = float((player.get("skills") or {}).get("ship", 0))
        base_cost = upgrade_cost_for_next_level(tier, level, ship_skill)
        if base_cost is not None and level < eff_max_level:
            next_cost = max(1, int(round(base_cost * (1.0 - cost_reduction))))
            embed.add_field(name="Next Upgrade Cost", value=f"{next_cost:,} Scrap", inline=True)

        await ctx.send(embed=embed)

    async def _upgrade(self, ctx, player: dict):
        ensure_ship(player)
        ship = player["ship"]
        if not ship.get("owned"):
            await ctx.send(f"{ctx.author.mention}, buy a Starter Ship with `!buy starter ship` first.")
            return

        # Soldier effective max level
        s_eff = soldier_effects(player)
        eff_max_level = MAX_LEVEL + int(s_eff.get("ship_max_level_bonus", 0))
        if ship["level"] >= eff_max_level:
            await ctx.send(f"{ctx.author.mention}, your ship is already max level.")
            return

        # Base cost then apply Soldier reduction
        ship_skill = float((player.get("skills") or {}).get("ship", 0))
        base_cost = upgrade_cost_for_next_level(ship["tier"], ship["level"], ship_skill)
        if base_cost is None:
            await ctx.send(f"{ctx.author.mention}, your ship is already max level.")
            return

        cost = max(1, int(round(base_cost * (1.0 - float(s_eff.get("ship_upgrade_cost_reduction", 0.0))))))
        if player.get("Scrap", 0) < cost:
            await ctx.send(f"{ctx.author.mention}, you need {cost} Scrap to upgrade (you have {player.get('Scrap',0)}).")
            return

        player["Scrap"] -= cost
        ship["level"] += 1
        # Clamp in case of external changes
        ship["level"] = min(ship["level"], eff_max_level)
        save_profile(ctx.author.id, player)

        await ctx.send(
            f"🛠️ {ctx.author.mention} upgraded their ship to Level {ship['level']} for {cost} Scrap."
        )

    async def _refit(self, ctx, player: dict, rest: str):
        """
        Tier-up attempt. Modes:
          • !ship refit solo          → solo refit (lower success)
          • !ship refit @ally         → duo refit (same tier required)
        At MK10, refit always rerolls type only (no tier-up, attempts not counted).
        """
        ensure_ship(player)
        ship = player["ship"]
        if not ship.get("owned"):
            await ctx.send(f"{ctx.author.mention}, buy a Starter Ship with `!buy starter ship` first.")
            return

        cur_tier = int(ship.get("tier", 1))

        # Parse flags and optional ally mention
        tokens = (rest or "").lower().split()
        solo_mode = "solo" in tokens
        ally = None
        if not solo_mode and ctx.message.mentions:
            cand = ctx.message.mentions[0]
            if cand.id != ctx.author.id:  # ignore self-mention
                ally = cand
        # Solo attempts count as 0.5 toward pity; Duo as 1.0
        attempt_unit = 1.0 if ally else 0.5

        # Cooldown helpers
        now = int(time.time())
        cd_key = "ship refit"
        cd_secs = int(command_cooldowns.get(cd_key, 28800))
        def fmt_remaining(uid):
            exp = get_cooldown(uid, cd_key)
            rem = max(0, exp - now)
            return rem, str(timedelta(seconds=rem))

        def fmt_attempts(val) -> str:
            try:
                f = float(val)
                # Show .5 if fractional, else int
                return f"{f:.1f}".rstrip("0").rstrip(".")
            except Exception:
                return str(val)

        # If no ally and not solo → show info and exit
        if not ally and not solo_mode:
            # READ as float to preserve fractional progress
            attempts = float(ship.get("attempts", {}).get(str(cur_tier), 0))
            rem, human = fmt_remaining(ctx.author.id)
            cd_line = f"• Refit Cooldown: {human} remaining" if rem > 0 else "• Refit Cooldown: Ready"
            mk10_note = "• At MK10, refit rerolls your ship type only (no tier-up, attempts not counted)." if cur_tier >= MAX_TIER else ""
            await ctx.send(
                "🛠️ Ship Refit — How it works:\n"
                "• Use `!ship refit solo` to attempt refit alone (lower success rate), or tag an ally of the same tier: `!ship refit @User`.\n"
                "• Both players must confirm within 15 seconds (duo).\n"
                "• Each player rolls their own success — one may tier up while the other doesn’t.\n"
                "• Your ship type will be reassigned on refit (success or failure). If you used a Ship Token, your type won’t change on the next refit.\n"
                f"• Attempts used at {mk_name(cur_tier).upper()}: {fmt_attempts(attempts)}\n"
                f"{cd_line}\n"
                f"{mk10_note}"
            )
            return

        # Ally checks (duo only)
        ally_profile = None
        if ally:
            ally_profile = load_profile(str(ally.id))
            if not ally_profile:
                await ctx.send(f"{ctx.author.mention}, {ally.mention} doesn’t have a profile.")
                return
            ensure_ship(ally_profile)
            if not has_ship(ally_profile):
                await ctx.send(f"{ctx.author.mention}, {ally.mention} doesn’t own a ship.")
                return
            # Enforce same-tier refit (duo)
            if int(ally_profile["ship"]["tier"]) != cur_tier:
                await ctx.send(
                    f"❌ Both ships must be the same tier to refit.\n"
                    f"Your tier: {mk_name(cur_tier).upper()} • {ally.display_name}'s tier: {mk_name(ally_profile['ship']['tier']).upper()}"
                )
                return

        # Check cooldown(s)
        self_rem, self_human = fmt_remaining(ctx.author.id)
        if self_rem > 0:
            await ctx.send(f"⏳ {ctx.author.mention}, you must wait {self_human} before refitting again.")
            return
        if ally:
            ally_rem, ally_human = fmt_remaining(ally.id)
            if ally_rem > 0:
                await ctx.send(f"⏳ {ally.mention} must wait {ally_human} before refitting again.")
                return

        # Attempts state (NO LOCKOUT — pity system)
        attempts_self = float(ship.get("attempts", {}).get(str(cur_tier), 0))
        max_at = max_attempts_for_tier(cur_tier)
        attempts_ally = 0.0
        if ally:
            attempts_ally = float(ally_profile["ship"].get("attempts", {}).get(str(cur_tier), 0))

        # ===== Confirmation (15s) =====
        yset = {"y", "yes", "ok", "okay", "confirm"}
        nset = {"n", "no", "cancel", "stop"}
        next_tier = min(MAX_TIER, cur_tier + 1)

        async def wait_yes(user, label: str):
            def check(m):
                return (
                    m.channel.id == ctx.channel.id
                    and m.author.id == user.id
                    and m.content.lower().strip() in (yset | nset)
                )
            try:
                msg = await self.bot.wait_for("message", timeout=15.0, check=check)
            except asyncio.TimeoutError:
                return None
            return True if msg.content.lower().strip() in yset else False

        if solo_mode:
            # Solo confirmation
            title = "🚧 Refit Confirmation (Solo)"
            desc = (
                f"{ctx.author.mention}\n"
                f"Attempt refit to {mk_name(next_tier).upper()} "
                f"(solo has lower success chance)."
            )
            if cur_tier >= MAX_TIER:
                desc += "\nMK10 detected — this refit will reroll your ship type only."
            embed = discord.Embed(title=title, description=desc, color=discord.Color.orange())
            embed.add_field(
                name=f"{ctx.author.display_name} — Your Ship",
                value=(
                    f"• Tier: {mk_name(cur_tier).upper()}\n"
                    f"• Level: {ship['level']}\n"
                    f"• Type: {(ship.get('type') or 'None').title()}\n"
                    f"• Attempts at {mk_name(cur_tier).upper()}: {fmt_attempts(attempts_self)}"
                ),
                inline=False,
            )
            embed.set_footer(text="Type 'yes' to confirm or 'no' to cancel (15s).")
            await ctx.send(content=f"{ctx.author.mention}", embed=embed)
            p_res = await wait_yes(ctx.author, "you")
            if p_res is not True:
                reason = "timed out" if p_res is None else "declined"
                await ctx.send(f"❌ Refit canceled — {ctx.author.mention} {reason}.")
                return

        else:
            # Duo confirmation
            initiator_tier = mk_name(ship["tier"]).upper()
            initiator_level = ship["level"]
            initiator_type = (ship.get("type") or "None").title()
            ally_tier = mk_name(ally_profile["ship"]["tier"]).upper()
            ally_level = ally_profile["ship"]["level"]
            ally_type = (ally_profile["ship"].get("type") or "None").title()

            embed = discord.Embed(
                title="🚧 Refit Confirmation",
                description=(
                    f"{ctx.author.mention} + {ally.mention}\n"
                    f"Attempt refit to {mk_name(next_tier).upper()}.\n"
                    "Both must reply 'yes' within 15 seconds."
                ),
                color=discord.Color.orange(),
            )
            embed.add_field(
                name=f"{ctx.author.display_name} — Your Ship",
                value=(
                    f"• Tier: {initiator_tier}\n"
                    f"• Level: {initiator_level}\n"
                    f"• Type: {initiator_type}\n"
                    f"• Attempts at {mk_name(cur_tier).upper()}: {fmt_attempts(attempts_self)}"
                ),
                inline=True,
            )
            embed.add_field(
                name=f"{ally.display_name} — Ally Ship",
                value=(
                    f"• Tier: {ally_tier}\n"
                    f"• Level: {ally_level}\n"
                    f"• Type: {ally_type}\n"
                    f"• Attempts at {mk_name(cur_tier).upper()}: {fmt_attempts(attempts_ally)}"
                ),
                inline=True,
            )
            await ctx.send(content=f"{ctx.author.mention} {ally.mention}", embed=embed)

            p_res, a_res = await asyncio.gather(
                wait_yes(ctx.author, "you"), wait_yes(ally, "ally")
            )
            if p_res is not True or a_res is not True:
                reason = "timed out" if (p_res is None or a_res is None) else "declined"
                who = []
                if p_res is not True:
                    who.append(ctx.author.mention)
                if a_res is not True:
                    who.append(ally.mention)
                await ctx.send(f"❌ Refit canceled — {', '.join(who)} {reason}.")
                return

        # Set cooldown(s)
        set_cooldown(ctx.author.id, cd_key, now + cd_secs, ctx.author.name)
        if ally:
            set_cooldown(ally.id, cd_key, now + cd_secs, ally.display_name)

        # Helper: determine new type (Ship Token can lock once)
        def new_type_for(profile: dict) -> str | None:
            s = profile.get("ship", {}) or {}
            if s.pop("lock_type_once", False):
                profile["ship"] = s
                return s.get("type")
            return random.choice(SHIP_TYPES)

        # ===== Perform rolls (with pity) =====
        rng = random.Random()

        def pity_success(attempts: float, max_attempts: int, tier: int, unit: float) -> bool:
            if tier >= MAX_TIER:
                return False
            if not max_attempts:
                return False
            # Current attempt counts as `unit` toward the pity threshold
            return (float(attempts) + float(unit)) >= float(max_attempts)

        p_pity = pity_success(attempts_self, max_at, cur_tier, attempt_unit)
        p_success = False if cur_tier >= MAX_TIER else (True if p_pity else roll_tier_up(rng, cur_tier, duo=bool(ally is not None), allow_mismatch=False, same_tier=True))

        a_success = False
        a_pity = False
        if ally:
            a_pity = pity_success(attempts_ally, max_at, cur_tier, 1.0)
            a_success = False if cur_tier >= MAX_TIER else (True if a_pity else roll_tier_up(rng, cur_tier, duo=True, allow_mismatch=False, same_tier=True))

        p_old_level = ship["level"]
        a_old_level = ally_profile["ship"]["level"] if ally else p_old_level

        # Snapshot types BEFORE mutation for correct arrows
        old_type = (ship.get("type") or "None")
        ally_old_type = (ally_profile["ship"].get("type") or "None") if ally else None

        # Only compute/assign averaged level for DUO refits; SOLO never changes level
        if ally:
            avg_level = max(1, int(round((p_old_level + a_old_level) / 2)))

        # Soldier clamp for duo averaged level
        s_eff_self = soldier_effects(player)
        s_eff_ally = soldier_effects(ally_profile) if ally else {}

        # Apply player result
        attempts_map = ship.setdefault("attempts", {})
        if cur_tier < MAX_TIER:
            if p_success:
                new_tier = min(MAX_TIER, cur_tier + 1)
                ship["tier"] = new_tier
                if ally:
                    p_eff_max = MAX_LEVEL + int(s_eff_self.get("ship_max_level_bonus", 0))
                    ship["level"] = min(avg_level, p_eff_max)
                # Initialize next tier attempts if absent
                attempts_map.setdefault(str(new_tier), attempts_map.get(str(new_tier), 0.0) or 0.0)
            else:
                # Progress pity by attempt_unit (0.5 solo, 1.0 duo)
                attempts_map[str(cur_tier)] = float(attempts_self) + float(attempt_unit)
        # Always (re)assign type on refit
        ship["type"] = new_type_for(player)

        # Apply ally result
        if ally:
            ally_attempts_map = ally_profile["ship"].setdefault("attempts", {})
            if cur_tier < MAX_TIER:
                if a_success:
                    ally_new_tier = min(MAX_TIER, cur_tier + 1)
                    ally_profile["ship"]["tier"] = ally_new_tier
                    a_eff_max = MAX_LEVEL + int(s_eff_ally.get("ship_max_level_bonus", 0))
                    ally_profile["ship"]["level"] = min(avg_level, a_eff_max)
                    ally_attempts_map.setdefault(str(ally_new_tier), ally_attempts_map.get(str(ally_new_tier), 0.0) or 0.0)
                else:
                    ally_attempts_map[str(cur_tier)] = float(attempts_ally) + 1.0
            ally_profile["ship"]["type"] = new_type_for(ally_profile)

        # ===== Results Embed =====
        def fmt_tier(t): return mk_name(t).upper()
        def arrow(a, b): return f"{a} → {b}" if a != b else f"{a} (unchanged)"

        color = (
            discord.Color.green() if (p_success and a_success)
            else (discord.Color.orange() if (p_success or a_success) else discord.Color.red())
        )

        p_label = '✅ Success' if p_success else ('🔁 Type Reroll' if cur_tier >= MAX_TIER else '❌ Failed')
        a_label = '✅ Success' if a_success else ('🔁 Type Reroll' if cur_tier >= MAX_TIER else '❌ Failed')

        # Compute displayed attempts after this action (fail shows +unit progress)
        next_self_attempts = attempts_self if (p_success or cur_tier >= MAX_TIER) else (float(attempts_self) + float(attempt_unit))
        next_ally_attempts = attempts_ally if not ally or (a_success or cur_tier >= MAX_TIER) else (float(attempts_ally) + 1.0)

        if ally:
            self_after = {
                "tier": ship.get("tier"),
                "level": ship.get("level"),
                "type": (ship.get("type") or "None"),
                "attempts": fmt_attempts(next_self_attempts),
            }
            ally_after = {
                "tier": ally_profile["ship"].get("tier"),
                "level": ally_profile["ship"].get("level"),
                "type": (ally_profile["ship"].get("type") or "None"),
                "attempts": fmt_attempts(next_ally_attempts),
            }
            embed = discord.Embed(
                title="🛠️ Refit Results (Duo)",
                description=f"{ctx.author.mention} + {ally.mention}",
                color=color,
            )
            embed.add_field(
                name=f"{ctx.author.display_name} — Your Ship",
                value=(
                    f"• Result: {p_label}\n"
                    f"• Tier: {arrow(fmt_tier(cur_tier), fmt_tier(self_after['tier']))}\n"
                    f"• Level: {arrow(p_old_level, self_after['level'])}\n"
                    f"• Type: {arrow((old_type or 'None').title(), self_after['type'].title())}\n"
                    f"• Attempts at {fmt_tier(cur_tier)}: {self_after['attempts']}"
                ),
                inline=True,
            )
            embed.add_field(
                name=f"{ally.display_name} — Ally Ship",
                value=(
                    f"• Result: {a_label}\n"
                    f"• Tier: {arrow(fmt_tier(cur_tier), fmt_tier(ally_after['tier']))}\n"
                    f"• Level: {arrow(a_old_level, ally_after['level'])}\n"
                    f"• Type: {arrow(((ally_old_type or 'None') if ally_old_type is not None else 'None').title(), ally_after['type'].title())}\n"
                    f"• Attempts at {fmt_tier(cur_tier)}: {ally_after['attempts']}"
                ),
                inline=True,
            )
            await ctx.send(content=f"{ctx.author.mention} {ally.mention}", embed=embed)
        else:
            self_after = {
                "tier": ship.get("tier"),
                "level": ship.get("level"),  # unchanged for solo
                "type": (ship.get("type") or "None"),
                "attempts": fmt_attempts(next_self_attempts),
            }
            embed = discord.Embed(
                title="🛠️ Refit Results (Solo)",
                description=f"{ctx.author.mention}",
                color=(discord.Color.green() if p_success else (discord.Color.blue() if cur_tier >= MAX_TIER else discord.Color.red())),
            )
            embed.add_field(
                name=f"{ctx.author.display_name} — Your Ship",
                value=(
                    f"• Result: {p_label}\n"
                    f"• Tier: {arrow(fmt_tier(cur_tier), fmt_tier(self_after['tier']))}\n"
                    f"• Level: {arrow(p_old_level, self_after['level'])}\n"
                    f"• Type: {arrow((old_type or 'None').title(), self_after['type'].title())}\n"
                    f"• Attempts at {fmt_tier(cur_tier)}: {self_after['attempts']}"
                ),
                inline=False,
            )
            await ctx.send(content=f"{ctx.author.mention}", embed=embed)

        # Persist
        save_profile(ctx.author.id, player)
        if ally:
            save_profile(ally.id, ally_profile)

async def setup(bot):
    await bot.add_cog(Ship(bot))
