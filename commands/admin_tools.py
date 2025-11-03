import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.cooldowns import COOLDOWNS_FILE, active_cooldowns, save_cooldowns  # CHANGED
import importlib


class AdminTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Only the bot owner can run commands in this cog
    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)


    def _clear_user_cooldowns(self, user_id: int | str, command: str | None = None) -> int:
        uid = str(user_id)
        user_data = active_cooldowns.get(uid)
        if not user_data or not isinstance(user_data, dict):
            return 0

        # Ensure structure
        cooldowns = user_data.get("cooldowns")
        if not isinstance(cooldowns, dict):
            user_data["cooldowns"] = {}
            save_cooldowns()
            return 0

        cleared = 0
        if command:
            key = command.strip().lower()
            # keys are stored as given; normalize to lower to match your usage
            # try exact first, then lower-cased fallback
            if key in cooldowns:
                cooldowns.pop(key, None)
                cleared = 1
            elif command in cooldowns:
                cooldowns.pop(command, None)
                cleared = 1
        else:
            cleared = len(cooldowns)
            user_data["cooldowns"] = {}

        active_cooldowns[uid] = user_data
        save_cooldowns()
        return cleared

    @commands.command(name="clearcd", aliases=["cdclear", "cooldownclear"])
    @requires_profile()
    async def clear_cooldown(self, ctx, command: str | None = None, member: discord.Member | None = None):
        """
        Clear cooldowns.
        Usage:
          !clearcd                 → clear all your cooldowns
          !clearcd bossfight       → clear your bossfight cooldown
          !clearcd quest @User     → admin: clear @User's quest cooldown
        """
        target = member or ctx.author
        if target.id != ctx.author.id and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ You must be an Administrator to clear cooldowns for other users.")
            return

        cleared = self._clear_user_cooldowns(target.id, command)
        if command:
            await ctx.send(f"✅ Cleared {cleared} cooldown entry for {target.mention} (command: {command}).")
        else:
            await ctx.send(f"✅ Cleared all ({cleared}) cooldown entries for {target.mention}.")

    @commands.command(name="crewspawn", aliases=["forcecrew", "force_crew"])
    @requires_profile()
    async def crewspawn(self, ctx):
        """
        Admin: force a Crew applicant to appear (for yourself).
        Opens the normal hire prompt flow.
        """
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admins only.")
            return

        # Try to import the spawn system
        try:
            cs = importlib.import_module("systems.crew_sys")
        except Exception:
            await ctx.send("⚠️ Crew spawn system not available.")
            return

        # Monkeypatch spawn chance and capacity for this call
        old_chance = getattr(cs, "SPAWN_CHANCE", 0.03)
        old_cap_fn = getattr(cs, "capacity_for_sector", None)
        # capacity_for_sector is imported into the module at import time;
        # override the reference in the module so cap checks pass.
        cs.SPAWN_CHANCE = 1.0
        cs.capacity_for_sector = (lambda sector: 999)

        try:
            await cs.maybe_spawn_crew(ctx, source="admin-force")
        finally:
            # Restore previous settings
            cs.SPAWN_CHANCE = old_chance
            if old_cap_fn is not None:
                cs.capacity_for_sector = old_cap_fn

async def setup(bot):
    await bot.add_cog(AdminTools(bot))
