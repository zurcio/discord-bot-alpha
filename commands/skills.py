from __future__ import annotations
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.guards import require_no_lock
from core.skills import SKILLS
from core.skills import xp_required
from core.skills_hooks import perks_for, try_enable_overcharged
from core.constants import SKILLS_ENABLED

def _bar(cur: int, req: int, width: int = 18) -> str:
    if req <= 0: return "[]"  # avoid div by zero
    filled = int(width * min(1, cur / req))
    return "[" + "█"*filled + "·"*(width - filled) + "]"

class Skills(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="skills", aliases=["skill"])
    @requires_profile()
    @require_no_lock()
    async def skills_cmd(self, ctx):
        if not SKILLS_ENABLED:
            await ctx.send("Skills are currently disabled.")
            return
        p = ctx.player
        s = p.setdefault("skills", {})
        lines = []
        for name in SKILLS:
            node = s.setdefault(name, {"level": 1, "xp": 0})
            lvl = int(node.get("level", 1))
            xp = int(node.get("xp", 0))
            req = xp_required(name, lvl)
            lines.append(f"- {name.title():<9} L{lvl:<3} {xp:>6}/{req:<6} {_bar(xp, req)}")
        perks = perks_for(p)
        oc = "ON" if perks.get("overcharged") else "OFF"
        emb = discord.Embed(title="Skills", description="\n".join(lines), color=discord.Color.blurple())
        emb.set_footer(text=f"Overcharged: {oc}")
        await ctx.send(embed=emb)

    @commands.command(name="overcharge", aliases=["oc"])
    @requires_profile()
    @require_no_lock()
    async def overcharge_cmd(self, ctx):
        if not SKILLS_ENABLED:
            await ctx.send("Skills are currently disabled.")
            return
        p = ctx.player
        if try_enable_overcharged(p):
            await ctx.send("Overcharged enabled permanently. Post-100 scaling and overrides now apply.")
        else:
            await ctx.send("You must reach level 100 in all skills to enable Overcharged.")

async def setup(bot):
    await bot.add_cog(Skills(bot))
