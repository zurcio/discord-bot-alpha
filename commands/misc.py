import discord
import time
import math
from datetime import timedelta
from discord.ext import commands
from core.cooldowns import get_cooldown
from core.decorators import requires_profile
from core.guards import require_no_lock
from core.constants import COMMAND_GROUPS, GROUP_EMOJIS, COOLDOWN_COMMANDS, WORK_COMMANDS


EXTRA_COOLDOWNS = {"bossfight", "quest", "weekly", "lootbox"}  # add local cooldown-tracked commands


class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ====== COMMANDS LIST ======
    @commands.command(name="commands", aliases=["cmds", "cmd"])
    @requires_profile()
    @require_no_lock()
    async def commands_list(self, ctx):
        """Show all commands grouped, with cooldowns."""
        user_id = str(ctx.author.id)
        now = int(time.time())

        lines = ["**💻 Command Interface — Available Commands:**"]
        cooldown_set = set(COOLDOWN_COMMANDS) | EXTRA_COOLDOWNS

        for group_name, cmd_list in COMMAND_GROUPS.items():
            emoji = GROUP_EMOJIS.get(group_name, "🛠️")
            lines.append(f"\n{emoji} __**{group_name} Commands:**__")
            cooldown_cmds = []
            non_cooldown_cmds = []
            shown_special = set()  # prevent duplicate 'lootbox' rows in this group

            for cmd_name in cmd_list:
                if cmd_name == "work":
                    cooldown_expires = get_cooldown(user_id, "work")
                    work_display = ", ".join(f"`{c}`" for c in WORK_COMMANDS)
                    if now < cooldown_expires:
                        remaining = cooldown_expires - now
                        td = str(timedelta(seconds=math.ceil(remaining)))
                        lines.append(f"   🕒 {work_display} — shared cooldown: {td}")
                    else:
                        lines.append(f"   ✅ {work_display} — ready!")
                    continue

                # SPECIAL: show supply crate cooldown as 'buy supply crate' even though there is no command
                if cmd_name == "supply_crate" and "supply_crate" not in shown_special:
                    shown_special.add("supply_crate")
                    cooldown_expires = get_cooldown(user_id, "supply_crate")
                    if now < cooldown_expires:
                        remaining = cooldown_expires - now
                        td = str(timedelta(seconds=math.ceil(remaining)))
                        cooldown_cmds.append(f"🕒 `buy supply crate` — cooldown: {td}")
                    else:
                        cooldown_cmds.append(f"✅ `buy supply crate` — ready!")
                    continue

                cmd = self.bot.get_command(cmd_name)
                if not cmd:
                    # Skip unknown commands (we already handled special cases)
                    continue

                if cmd_name in cooldown_set:
                    cooldown_expires = get_cooldown(user_id, cmd_name)
                    if now < cooldown_expires:
                        remaining = cooldown_expires - now
                        td = str(timedelta(seconds=math.ceil(remaining)))
                        cooldown_cmds.append(f"🕒 `{cmd_name}` — cooldown: {td}")
                    else:
                        cooldown_cmds.append(f"✅ `{cmd_name}` — ready!")
                else:
                    non_cooldown_cmds.append(f"`{cmd_name}`")

            # Add cooldown commands (each on its own line)
            for entry in cooldown_cmds:
                lines.append(f"   {entry}")

            # Add non-cooldown commands (comma separated)
            if non_cooldown_cmds:
                lines.append("   " + ", ".join(non_cooldown_cmds))

        await ctx.send("\n".join(lines))


    # ====== READY COMMAND ======
    @commands.command(name="ready", aliases=["rd"])
    @requires_profile()
    @require_no_lock()
    async def ready(self, ctx):
        """Show only cooldown commands that are ready to use."""
        user_id = str(ctx.author.id)
        now = int(time.time())

        ready_lines = ["**✅ Commands Ready — Immediate Use:**"]
        cooldown_set = set(COOLDOWN_COMMANDS) | EXTRA_COOLDOWNS

        for cmd_name in sorted(cooldown_set):
            if cmd_name == "work":
                cooldown_expires = get_cooldown(user_id, "work")
                if now >= cooldown_expires:
                    work_display = ", ".join(f"`{c}`" for c in WORK_COMMANDS)
                    ready_lines.append(f"   🚀 {work_display}")
                continue

            # SPECIAL: supply crate pseudo-command readiness as 'buy supply crate'
            if cmd_name == "supply_crate":
                cooldown_expires = get_cooldown(user_id, "supply_crate")
                if now >= cooldown_expires:
                    ready_lines.append("   🚀 `buy supply crate`")
                continue

            cmd = self.bot.get_command(cmd_name)
            if not cmd:
                continue

            cooldown_expires = get_cooldown(user_id, cmd_name)
            if now >= cooldown_expires:
                ready_lines.append(f"   🚀 `{cmd_name}`")

        if len(ready_lines) == 1:
            ready_lines.append("   _No commands ready yet._")

        await ctx.send("\n".join(ready_lines))


async def setup(bot):
    await bot.add_cog(Misc(bot))