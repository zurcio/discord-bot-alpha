from discord.ext import commands
from core.decorators import requires_profile
from core.players import load_profile, save_profile
from core.guards import set_lock, clear_lock, require_no_lock
from systems.bossfight_sys import (
    ensure_party_on_same_boss_planet,
    load_boss_for_planet,
    check_requirements,
    confirm_participation,
    consume_keycard,
    run_combat,
    grant_boss_rewards,
    grant_boss_victory_rewards,   
)
import time
from datetime import timedelta
from core.cooldowns import get_cooldown, set_cooldown, command_cooldowns


class Bossfight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="bossfight", aliases=["bf"])
    @requires_profile(auto_save=False)
    @require_no_lock()
    async def bossfight(self, ctx, *members: commands.MemberConverter):
        unique_allies = []
        seen = set([ctx.author.id])
        for m in members:
            if m.id not in seen:
                seen.add(m.id)
                unique_allies.append(m)

        player_ids = [str(ctx.author.id)] + [str(m.id) for m in unique_allies]
        if len(player_ids) > 4:
            return await ctx.send("❌ You can only bring up to 3 allies (4 total).")

        # Load profiles
        profiles = {pid: load_profile(pid) for pid in player_ids}
        if any(p is None for p in profiles.values()):
            return await ctx.send("❌ One or more players do not have profiles.")

        # Ensure party alignment
        planet_id = await ensure_party_on_same_boss_planet(ctx, profiles)
        if planet_id is None:
            return

        boss = load_boss_for_planet(planet_id, len(player_ids))

        # Check per-player cooldowns
        now = int(time.time())
        cd_key = "bossfight"
        cd_secs = int(command_cooldowns.get(cd_key, 43200))
        blocked = []
        for pid in player_ids:
            exp = int(get_cooldown(pid, cd_key) or 0)
            if now < exp:
                rem = exp - now
                human = str(timedelta(seconds=rem))
                name = profiles[pid].get("username", f"user_{pid}")
                blocked.append(f"{name}: {human}")
        if blocked:
            return await ctx.send("⏳ Bossfight cooldowns:\n• " + "\n• ".join(blocked))

        if not await check_requirements(ctx, profiles, boss):
            return

        if not await confirm_participation(ctx, player_ids, boss["name"], self.bot):
            return

        # Set cooldowns for all participants after confirmation
        now = int(time.time())
        for pid in player_ids:
            uname = profiles[pid].get("username", f"user_{pid}")
            set_cooldown(pid, cd_key, now + cd_secs, uname)

        # Lock all participants until fight ends
        for pid in player_ids:
            set_lock(pid, lock_type="bossfight", allowed=set(), note=f"Bossfight vs {boss['name']}")

        try:
            # Consume keycards
            for pid in player_ids:
                profiles[pid] = consume_keycard(profiles[pid])

            # Run combat
            victory = await run_combat(ctx, profiles, player_ids, boss, self.bot)

            # Outcome
            if victory:
                await ctx.send(f"🏆 {boss['name']} was defeated! The path forward is open.")

                # Apply victory rewards per player (before planet advance so multipliers match current planet)
                for pid in player_ids:
                    res = grant_boss_victory_rewards(pid, profiles[pid], planet_id, boss, len(player_ids))
                    scrap = res["applied"]["scrap"]
                    xp = res["applied"]["xp"]
                    # Soldier skill feedback (optional concise message)
                    sxp = res.get("soldier", {}).get("xp", 0)
                    sup = res.get("soldier", {}).get("levels_gained", 0)
                    lvl = res.get("soldier", {}).get("level", 0)
                    soldier_msg = f" • ⚔️ Soldier +{sxp} XP" + (f" (L{lvl} +{sup})" if sup > 0 else "")
                    await ctx.send(f"• <@{pid}> earned 💰 {scrap:,} Scrap and ⭐ {xp:,} XP.{soldier_msg}")

                # Progression + warpdrive + quest cleanup
                for pid in player_ids:
                    if profiles[pid].get("active_quest"):
                        profiles[pid]["active_quest"] = None

                    warp_id, warp_name = grant_boss_rewards(pid, planet_id, profiles[pid])
                    moved_to = planet_id + 1
                    msg = f"🔓 {profiles[pid]['username']} advanced to Planet {moved_to}"
                    if warp_id:
                        msg += f" and received **{warp_name}**!"
                    await ctx.send(msg)

            else:
                await ctx.send(f"☠️ All players were defeated by {boss['name']}...")
                # No defeat penalty. Cooldowns were already applied above.


        finally:
            # Always clear locks and save
            for pid in player_ids:
                clear_lock(pid)
                save_profile(pid, profiles[pid])

async def setup(bot):
    await bot.add_cog(Bossfight(bot))
