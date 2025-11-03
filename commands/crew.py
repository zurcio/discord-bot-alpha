import time, discord
from discord.ext import commands
from core.decorators import requires_profile
from core.players import save_profile
from core.crew import ensure_crew_struct, capacity_for_sector, start_job, claim_job, JOB_SECONDS

def _find_by_code(player, code):
    code = (code or "").upper()
    for c in player.get("crew", []):
        if c.get("code", "").upper() == code:
            return c
    return None

class Crew(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="crew")
    @requires_profile()
    async def crew(self, ctx, action: str = None, *, rest: str = ""):
        player = ctx.player
        ensure_crew_struct(player)
        sector = int(player.get("sector") or 1)
        if sector < 3:
            await ctx.send("Crew unlocks at Sector 3.")
            return

        now = int(time.time())

        if not action:
            cap = capacity_for_sector(sector)
            lines = [f"Slots: {len(player['crew'])} / {cap}"]
            claimable = 0
            for c in player["crew"]:
                status = c.get("status", "idle")
                if status == "working":
                    ends = int(c.get("job_ends") or 0)
                    rem = max(0, ends - now)
                    lines.append(f"{c['code']}: {c['name']} [{c['type']}] — working, {rem//3600}h {(rem%3600)//60}m left")
                    if rem <= 0:
                        claimable += 1
                else:
                    lines.append(f"{c['code']}: {c['name']} [{c['type']}] — idle")
            if claimable:
                lines.append(f"{claimable} job(s) ready. Use !crew claim <id>.")
            await ctx.send("• " + "\n• ".join(lines))
            return

        action = action.lower()
        if action == "rename":
            parts = rest.split(" ", 1)
            if len(parts) < 2:
                await ctx.send("Usage: !crew rename <id> <name>")
                return
            cid, new_name = parts[0].strip(), parts[1].strip()
            c = _find_by_code(player, cid)
            if not c:
                await ctx.send("Invalid crew id.")
                return
            c["name"] = new_name[:32]
            save_profile(ctx.author.id, player)
            await ctx.send(f"Renamed {cid} to {new_name}.")
            return

        if action == "job":
            cid = rest.strip()
            if not cid:
                await ctx.send("Usage: !crew job <id>")
                return
            c = _find_by_code(player, cid)
            if not c:
                await ctx.send("Invalid crew id.")
                return
            err = start_job(player, c, now)
            if err:
                await ctx.send(err)
                return
            save_profile(ctx.author.id, player)
            await ctx.send(f"Sent {c['code']} ({c['name']}) on a job. Returns in 4h.")
            return

        if action == "claim":
            cid = rest.strip()
            if not cid:
                await ctx.send("Usage: !crew claim <id>")
                return
            c = _find_by_code(player, cid)
            if not c:
                await ctx.send("Invalid crew id.")
                return
            ok, reward = claim_job(player, c, sector=int(player.get("sector") or 1), planet=int(player.get("current_planet") or 1), now=now)
            if not ok:
                await ctx.send("Not ready yet.")
                return
            save_profile(ctx.author.id, player)
            # Simple summary
            parts = []
            if reward.get("scrap"): parts.append(f"Scrap {reward['scrap']:,}")
            if reward.get("xp"): parts.append(f"XP {reward['xp']:,}")
            if reward.get("items"):
                items_str = ", ".join(f"{k} x{v}" for k, v in reward["items"].items())
                parts.append(items_str)
            await ctx.send(f"Claimed job rewards for {c['code']} — " + ("; ".join(parts) or "None"))
            return

        await ctx.send("Unknown subcommand. Use: !crew, !crew job <id>, !crew claim <id>, !crew rename <id>.")

async def setup(bot):
    await bot.add_cog(Crew(bot))