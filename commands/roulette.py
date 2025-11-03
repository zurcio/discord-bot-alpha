import random
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.players import save_profile
from core.guards import require_no_lock
from core.quest_progress import update_quest_progress_for_gambling 
from core.skills_hooks import award_skill


class Roulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="roulette", aliases=["roul"])
    @requires_profile()
    @require_no_lock()
    async def roulette(self, ctx, bet_type: str = None, bet_amount: str = None):
        """
        🎰 Try your luck at Scrap Roulette!
        Usage:
          !roulette <bet_type> <amount>
        Example:
          !roulette red 100
          !roulette even 500
          !roulette 17 200
        """

        player = ctx.player
        scrap = player.get("Scrap", 0)

        # ✅ Valid bet options
        bet_type = (bet_type or "").lower()
        valid_bets = ["red", "black", "even", "odd"] + [str(i) for i in range(0, 37)]
        
        if bet_type == None:
            await ctx.send(
                "🎰 **Roulette Instructions:**\n"
                "`!roulette <bet_type> <amount>`\n\n"
                "**Bet Types:**\n"
                "• `red` / `black` → 2x payout (48% win chance)\n"
                "• `even` / `odd` → 2x payout (48% win chance)\n"
                "• `0-36` (number) → 36x payout (2.7% win chance)\n\n"
                "Example: `!roulette red 100`\n"
                "You can also bet `all` or `half` your Scrap.\n"
                f"Your current balance: **{scrap:,} Scrap**"
            )
            return

        if bet_amount:
            if bet_amount.isdigit():
                bet_amount = int(bet_amount)
            elif bet_amount and bet_amount.lower() == "all":
                bet_amount = scrap
            elif bet_amount and bet_amount.lower() == "half":
                bet_amount = scrap // 2
        else:
            await ctx.send(
                "🎰 **Roulette Instructions:**\n"
                "`!roulette <bet_type> <amount>`\n\n"
                "**Bet Types:**\n"
                "• `red` / `black` → 2x payout (48% win chance)\n"
                "• `even` / `odd` → 2x payout (48% win chance)\n"
                "• `0-36` (number) → 36x payout (2.7% win chance)\n\n"
                "Example: `!roulette red 100`\n"
                "You can also bet `all` or `half` your Scrap.\n"
                f"Your current balance: **{scrap:,} Scrap**"
            )
            return

        if bet_type not in valid_bets or not bet_amount:
            await ctx.send(
                "🎰 **Roulette Instructions:**\n"
                "`!roulette <bet_type> <amount>`\n\n"
                "**Bet Types:**\n"
                "• `red` / `black` → 2x payout (48% win chance)\n"
                "• `even` / `odd` → 2x payout (48% win chance)\n"
                "• `0-36` (number) → 36x payout (2.7% win chance)\n\n"
                "Example: `!roulette red 100`\n"
                "You can also bet `all` or `half` your Scrap.\n"
                f"Your current balance: **{scrap:,} Scrap**"
            )
            return

        # Validate amount
        if bet_amount <= 0:
            await ctx.send(f"{ctx.author.mention}, your bet must be greater than 0 Scrap!")
            return

        if bet_amount > scrap:
            await ctx.send(f"{ctx.author.mention}, you don’t have enough Scrap to place that bet!")
            return

        # Deduct upfront
        player["Scrap"] -= bet_amount

        # Simulate roulette spin (0-36)
        spin_result = random.randint(0, 36)
        color = "red" if spin_result in (
            1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36
        ) else ("black" if spin_result != 0 else "green")

        # Determine outcome
        win = False
        multiplier = 0

        if bet_type.isdigit():
            if int(bet_type) == spin_result:
                win, multiplier = True, 36
        elif bet_type == "red" and color == "red":
            win, multiplier = True, 2
        elif bet_type == "black" and color == "black":
            win, multiplier = True, 2
        elif bet_type == "even" and spin_result != 0 and spin_result % 2 == 0:
            win, multiplier = True, 2
        elif bet_type == "odd" and spin_result % 2 == 1:
            win, multiplier = True, 2

        embed = discord.Embed(
            title="🎰 Roulette Result",
            color=discord.Color.green() if win else discord.Color.red()
        )
        embed.add_field(name="Spin Result", value=f"{spin_result} ({color.capitalize()})", inline=False)

        if win:
            winnings = bet_amount * multiplier
            player["Scrap"] += winnings
            # NEW: Gambler XP (flat)
            lvl, ups = award_skill(ctx, "gambler", 5)
            xp_note = f" • 🎲 Gambler +5 XP" + (f" (L{lvl} +{ups})" if ups > 0 else "")
            embed.add_field(
                name="💰 You Win!",
                value=f"You won **{winnings:,} Scrap** (x{multiplier})!{xp_note}",
                inline=False
            )


            # QUEST PROGRESSION - Gambling (net positive)
            prev = (player.get("active_quest") or {}).get("progress", 0)
            net = winnings - bet_amount
            if net > 0:
                completed = update_quest_progress_for_gambling(ctx.player, net)
                q = player.get("active_quest") or {}
                if q and not q.get("completed", False):
                    newp = int(q.get("progress", 0))
                    goal = int(q.get("goal", 0))
                    if newp > prev:
                        await ctx.send(f"🎰 Quest Progress: {newp:,} / {goal:,} Scrap won.")
                elif completed:
                    await ctx.send("🎰 Quest Complete! Return with `!quest` to claim your rewards.")
            
                save_profile(ctx.author.id, player)

        else:
            embed.add_field(name="💀 You Lost", value=f"You lost **{bet_amount:,} Scrap**.", inline=False)

        embed.add_field(name="Current Balance", value=f"{player['Scrap']:,} Scrap", inline=False)
        embed.set_footer(text=f"Bet Type: {bet_type.capitalize()} | Player: {player['username']}")

        save_profile(ctx.author.id, player)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Roulette(bot))
