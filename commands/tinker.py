from discord.ext import commands
from core.decorators import requires_profile, requires_planet
from core.players import save_profile
from systems.tinker_sys import apply_tinker, tinker_cost_for_planet
from core.guards import require_no_lock
# NEW
import random
from core.skills_hooks import tinkerer_effects, award_skill, is_player_overcharged

# NEW: Tier → base Tinkerer XP (tune freely)
_TINKER_TIER_XP = {
    "normal": 0,
    "good": 1,
    "great": 2,
    "excellent": 3,
    "mythic": 4,
    "legendary": 5,
    "molecular": 6,
    "atomic": 7,
    "neutronic": 8,
    "protonic": 10,
    "quarkic": 12,
    "sophonic": 15,
    "quantum": 20,
}

def _planet_xp_mult(effective_planet: int) -> int:
    if effective_planet >= 10:
        return 1000
    if 7 <= effective_planet <= 9:
        return 100
    return 1

class Tinker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="tinker")
    @requires_profile()
    @requires_planet(2)
    @require_no_lock()
    async def tinker(self, ctx, slot: str = None):
        """
        Enhance your equipped weapon or armor.
        Usage: !tinker weapon | !tinker armor
        Unlocks at Planet 2. Costs Scrap based on your progression (higher at 7 and 10).
        """
        player = ctx.player
        max_p = int(player.get("max_unlocked_planet", 1) or 1)
        overcharged = is_player_overcharged(player)
        eff_p = 10 if overcharged else max_p

        if slot is None or slot.lower() not in ("weapon", "armor"):
            cost = tinker_cost_for_planet(eff_p)
            await ctx.send(
                f"{ctx.author.mention}, usage: `!tinker weapon` or `!tinker armor`.\n"
                f"Cost: {cost} Scrap. Higher planets improve enhancement odds."
            )
            return

        # We will rely on apply_tinker to deduct cost up front (using effective planet)
        cost = tinker_cost_for_planet(eff_p)
        before_scrap = int(player.get("Scrap", 0))

        ok, tier, buff, new_val, name = apply_tinker(player, slot, effective_planet=eff_p)
        if not ok:
            eq = (player.get("equipped") or {}).get(slot.lower())
            if not eq:
                await ctx.send(f"{ctx.author.mention}, you must equip a {slot} first.")
                return
            if before_scrap < cost:
                await ctx.send(f"{ctx.author.mention}, you need {cost} Scrap to tinker.")
                return
            await ctx.send(f"{ctx.author.mention}, unable to tinker that item right now.")
            return

        # Scrap refund chance (post‑100): on success, credit double the cost (net +cost)
        eff = tinkerer_effects(player)
        refund_chance = float(eff.get("tinker_scrap_refund_chance", 0.0))
        refunded = False
        if refund_chance > 0.0 and random.random() < refund_chance:
            player["Scrap"] = int(player.get("Scrap", 0)) + (2 * int(cost))
            refunded = True

        # Tinkerer XP: base by tier × planet multiplier (Overcharged → P10)
        base_xp = int(_TINKER_TIER_XP.get(str(tier).lower(), 10))
        mult = _planet_xp_mult(eff_p)
        tinker_xp = base_xp * mult
        new_lvl, ups = award_skill(ctx, "tinkerer", tinker_xp)

        save_profile(str(ctx.author.id), player)
        arrow = "⚔️" if slot.lower() == "weapon" else "🛡️"
        refund_note = " • 💸 You gained Scrap!! what just happened? +{:,}".format(cost) if refunded else ""
        xp_note = f" • 🧪 Tinkerer +{tinker_xp} XP" + (f" (L{new_lvl} +{ups})" if ups > 0 else "")
        await ctx.send(
            f"{ctx.author.mention} spent **{cost}** Scrap to tinker with their **{name}** ({slot}) → "
            f"enhancement: **{str(tier).title()}** (+{int(buff*100)}%) {arrow} New {slot.title()} Stat: **{new_val}**"
            f"{refund_note} {xp_note}"
        )

async def setup(bot):
    await bot.add_cog(Tinker(bot))