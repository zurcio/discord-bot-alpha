import asyncio
import random
import time
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.guards import require_no_lock
from core.players import load_profile, save_profile
from core.quest_progress import update_quest_progress_for_gambling
from core.skills_hooks import award_player_skill


TRACK_LEN = 24
TICK_SEC = 0.9
LOBBY_SECONDS = 30
HOUSE_RAKE = 0.10  # 10% house edge from the total pool

def render_track(horses, positions):
    lines = []
    header = "🏁 Horse Race — first to the finish line wins!"
    for i, h in enumerate(horses):
        pos = min(positions[i], TRACK_LEN)
        name = h["name"]
        emoji = h["emoji"]
        left = "-" * pos
        right = "-" * (TRACK_LEN - pos)
        line = f"{i+1}. {emoji} {name:<11} |{left}🐎{right}| 🏁"
        lines.append(line)
    return "```\n" + header + "\n\n" + "\n".join(lines) + "\n```"

def render_lobby(horses, bets_view):
    lines = []
    lines.append("🎲 Place your bets! Type: bet <#|name> <amount>\nExample: bet 2 500 or bet Ghostzapper 1000")
    lines.append(f"Lobby closes in {bets_view['remaining']}s.")
    lines.append("")
    for i, h in enumerate(horses):
        total = sum(b["amount"] for b in bets_view["bets"].values() if b["horse"] == i)
        lines.append(f"{i+1}. {h['emoji']} {h['name']:<11} — Pool: {total:,} Scrap")
    # Bettors list (first 8)
    bettors = list(bets_view["bets"].keys())
    if bettors:
        lines.append("")
        lines.append("Bettors:")
        shown = 0
        for uid, b in bets_view["bets"].items():
            uname = b.get("name", f"user_{uid}")
            lines.append(f"- {uname}: {b['amount']:,} on {horses[b['horse']]['name']}")
            shown += 1
            if shown >= 8:
                lines.append(f"...and {len(bettors) - 8} more")
                break
    return "```\n" + "\n".join(lines) + "\n```"

class Race(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_channels = set()  # prevent concurrent races per channel

    @commands.command(name="race", help="Start an animated horse race with betting.")
    @requires_profile()
    @require_no_lock()
    async def race(self, ctx):
        # Prevent concurrent race in the same channel
        if ctx.channel.id in self.active_channels:
            await ctx.send("⚠️ A race is already running in this channel.")
            return

        self.active_channels.add(ctx.channel.id)
        try:
            horses = [
                {"name": "Ghostzapper", "emoji": "🐎"},
                {"name": "Secretariat", "emoji": "🐴"},
                {"name": "Justify",     "emoji": "🦄"},
                {"name": "Pharaoh",     "emoji": "🐎"},
            ]
            # Name lookup (case-insensitive)
            name_to_index = {h["name"].lower(): i for i, h in enumerate(horses)}

            # 1) Open betting lobby
            positions = [0] * len(horses)
            lobby_msg = await ctx.send("Preparing track...")
            await lobby_msg.edit(content=render_track(horses, positions))

            bets = {}  # user_id -> {"horse": index, "amount": int, "name": str}
            end_at = time.time() + LOBBY_SECONDS

            # Instruction/summary message
            info_msg = await ctx.send(render_lobby(horses, {"bets": bets, "remaining": LOBBY_SECONDS}))

            async def handle_bet(m: discord.Message):
                # Ignore other channels/bots
                if m.channel.id != ctx.channel.id or m.author.bot:
                    return
                content = m.content.strip()
                if not content.lower().startswith("bet "):
                    return
                parts = content.split()
                if len(parts) < 3:
                    await ctx.send(f"{m.author.mention} Usage: bet <#|name> <amount>")
                    return
                target = parts[1].strip().lower()
                try:
                    amt = int(parts[2])
                except ValueError:
                    await ctx.send(f"{m.author.mention} Amount must be a number.")
                    return
                if amt <= 0:
                    await ctx.send(f"{m.author.mention} Amount must be positive.")
                    return

                # Resolve horse
                horse_idx = None
                if target.isdigit():
                    idx = int(target) - 1
                    if 0 <= idx < len(horses):
                        horse_idx = idx
                if horse_idx is None:
                    horse_idx = name_to_index.get(target)

                if horse_idx is None:
                    await ctx.send(f"{m.author.mention} Unknown horse. Use a number 1-{len(horses)} or a valid name.")
                    return

                # Record/overwrite bet (we’ll clamp to wallet at lock-in)
                bets[str(m.author.id)] = {
                    "horse": horse_idx,
                    "amount": int(amt),
                    "name": m.author.display_name,
                }
                await ctx.message.add_reaction("✅") if m.author.id == ctx.author.id else None

            # Collect bets with a rolling timeout
            while True:
                remaining = int(max(0, end_at - time.time()))
                try:
                    msg = await self.bot.wait_for("message", timeout=1.0, check=lambda m: m.channel.id == ctx.channel.id)
                    await handle_bet(msg)
                except asyncio.TimeoutError:
                    pass

                # Update lobby every ~2s
                if remaining % 2 == 0:
                    try:
                        await info_msg.edit(content=render_lobby(horses, {"bets": bets, "remaining": remaining}))
                    except discord.HTTPException:
                        pass

                if time.time() >= end_at:
                    break

            # 2) Lock-in: validate and deduct bets (clamped to wallet)
            if not bets:
                await ctx.send("No bets placed. Running an exhibition race for fun.")
            locked_bets = {}  # user_id -> {"horse": idx, "amount": locked_amount, "name": str}
            pool = 0
            for uid, entry in list(bets.items()):
                profile = load_profile(str(uid)) or {}
                have = int(profile.get("Scrap", 0) or 0)
                bet_amt = min(entry["amount"], have)
                if bet_amt <= 0:
                    continue
                # Deduct and save immediately
                profile["Scrap"] = have - bet_amt
                save_profile(str(uid), profile)
                locked_bets[uid] = {"horse": entry["horse"], "amount": bet_amt, "name": entry["name"]}
                pool += bet_amt

            if pool <= 0:
                await ctx.send("⚠️ All bets were invalid or had insufficient Scrap. Running an exhibition race.")
                locked_bets.clear()

            # 3) Animate the race
            race_msg = await ctx.send(render_track(horses, positions))
            winner_idx = None
            while winner_idx is None:
                await asyncio.sleep(TICK_SEC)
                for i in range(len(horses)):
                    step = random.choice([0, 1, 1, 1, 2, 2, 3])
                    positions[i] += step
                    if positions[i] >= TRACK_LEN and winner_idx is None:
                        winner_idx = i
                try:
                    await race_msg.edit(content=render_track(horses, positions))
                except discord.HTTPException:
                    pass

            # Determine winners (ties allowed)
            max_pos = max(positions)
            winners = [i for i, p in enumerate(positions) if p >= max_pos]
            if len(winners) == 1:
                await ctx.send(f"🏆 Winner: {horses[winners[0]]['emoji']} {horses[winners[0]]['name']}!")
            else:
                names = ", ".join(f"{horses[i]['emoji']} {horses[i]['name']}" for i in winners)
                await ctx.send(f"🤝 Photo finish! Winners: {names}")

            # 4) Settle payouts (pari-mutuel)
            if locked_bets:
                winners_total = sum(b["amount"] for b in locked_bets.values() if b["horse"] in winners)
                if winners_total <= 0:
                    await ctx.send(f"House keeps the pool of {pool:,} Scrap. Better luck next time.")
                else:
                    payout_pool = int(pool * (1.0 - HOUSE_RAKE))
                    lines = [f"🏦 Pool: {pool:,} Scrap | Rake: {int(HOUSE_RAKE*100)}% | Payout: {payout_pool:,} Scrap"]
                    # Payout proportionally; all winning bettors get flat Gambler XP
                    for uid, b in locked_bets.items():
                        if b["horse"] not in winners:
                            continue
                        share = b["amount"] / winners_total
                        payout = int(round(payout_pool * share))
                        profile = load_profile(str(uid)) or {}
                        before = int(profile.get("Scrap", 0) or 0)
                        profile["Scrap"] = before + payout

                        # Quest progress (net positive only)
                        net = payout - b["amount"]
                        if net > 0:
                            update_quest_progress_for_gambling(profile, net)

                        # NEW: Gambler XP (flat +25 per winning bettor)
                        award_player_skill(profile, "gambler", 25)
                        save_profile(str(uid), profile)

                        hname = horses[b["horse"]]["name"]
                        lines.append(f"• {b['name']}: +{payout:,} Scrap (bet {b['amount']:,} on {hname}) • 🎲 Gambler +25 XP")

                    await ctx.send("\n".join(lines))


        finally:
            self.active_channels.discard(ctx.channel.id)

async def setup(bot):
    await bot.add_cog(Race(bot))

# import asyncio
# import random
# import discord
# from discord.ext import commands
# from core.decorators import requires_profile
# from core.guards import require_no_lock

# TRACK_LEN = 24
# TICK_SEC = 0.9

# def render_track(horses, positions):
#     lines = []
#     header = "🏁 Horse Race — first to the finish line wins!"
#     for i, h in enumerate(horses):
#         pos = min(positions[i], TRACK_LEN)
#         name = h["name"]
#         emoji = h["emoji"]
#         left = "-" * pos
#         right = "-" * (TRACK_LEN - pos)
#         # Finish line marker
#         line = f"{emoji} {name:<11} |{left}🐎{right}| 🏁"
#         lines.append(line)
#     return "```\n" + header + "\n\n" + "\n".join(lines) + "\n```"

# class Race(commands.Cog):
#     def __init__(self, bot):
#         self.bot = bot

#     @commands.command(name="race", help="Start an animated horse race.")
#     @requires_profile()
#     @require_no_lock()
#     async def race(self, ctx):
#         horses = [
#             {"name": "Ghostzapper", "emoji": "🐎"},
#             {"name": "Secretariat", "emoji": "🐴"},
#             {"name": "Justify",  "emoji": "🦄"},
#             {"name": "Pharaoh",  "emoji": "🐎"},
#         ]
#         positions = [0] * len(horses)
#         msg = await ctx.send("Preparing track...")

#         # Initial render
#         await msg.edit(content=render_track(horses, positions))

#         # Animate until someone reaches finish
#         winner_idx = None
#         while winner_idx is None:
#             await asyncio.sleep(TICK_SEC)

#             # Random advances with slight variance
#             for i in range(len(horses)):
#                 # Bias: small steady progress, occasional burst
#                 step = random.choice([0, 1, 1, 1, 2, 2, 3])
#                 positions[i] += step
#                 if positions[i] >= TRACK_LEN and winner_idx is None:
#                     winner_idx = i

#             await msg.edit(content=render_track(horses, positions))

#         # Determine winners (photo finish ties)
#         max_pos = max(positions)
#         winners = [i for i, p in enumerate(positions) if p >= max_pos]
#         if len(winners) == 1:
#             await ctx.send(f"🏆 Winner: {horses[winners[0]]['emoji']} {horses[winners[0]]['name']}!")
#         else:
#             names = ", ".join(f"{horses[i]['emoji']} {horses[i]['name']}" for i in winners)
#             await ctx.send(f"🤝 Photo finish! Winners: {names}")

# async def setup(bot):
#     await bot.add_cog(Race(bot))