import discord
from discord.ext import commands
from core.bank import ensure_bank
from core.decorators import requires_profile
from core.players import calculate_combat_stats, load_profile  # added load_profile
from core.utils import get_max_health, get_max_oxygen, make_progress_bar
from core.shared import load_json
from core.constants import PLANETS_FILE, ITEMS_FILE
from core.items import get_item_by_id
from core.guards import require_no_lock
from core.bank import ensure_bank, compute_bank_boost_percent
from core.sector import ensure_sector, sector_bonus_percent

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="profile", aliases=["me", "stats", "p", "pro"])
    @requires_profile()
    @require_no_lock()
    async def profile(self, ctx, member: discord.Member | None = None):
        """Show your profile, or another user's profile if mentioned."""
        # Resolve target
        target_user = member or ctx.author
        if member is None:
            player = ctx.player  # already loaded by requires_profile
        else:
            player = load_profile(str(member.id))
            if not player:
                await ctx.send(f"{target_user.mention} doesn't have a profile yet.")
                return

        current_xp = player.get("xp", 0)
        next_level_xp = max(1, player.get("level", 1)) * 100
        bar = make_progress_bar(current_xp, next_level_xp)

        equipped = player.get("equipped", {}) or {}
        enhancements = player.get("enhancements", {}) or {}

        # Load items and planets JSON
        items = load_json(ITEMS_FILE) or {}
        planets_root = load_json(PLANETS_FILE) or {}
        planets = planets_root.get("planets", planets_root) if isinstance(planets_root, dict) else {}

        # Fetch equipped item details
        weapon_id = equipped.get("weapon")
        armor_id = equipped.get("armor")
        weapon = get_item_by_id(items, weapon_id)
        armor = get_item_by_id(items, armor_id)

        # Enhancement labels
        w_tier = (enhancements.get(str(weapon_id)) or {}).get("tier")
        a_tier = (enhancements.get(str(armor_id)) or {}).get("tier")

        # Bank info
        bank = ensure_bank(player)
        boost = compute_bank_boost_percent(int(bank.get("balance", 0))) if bank.get("unlocked") else 0.0
        boost_str = f"{boost*100:.1f}%"

        def label(item, tier):
            if not item:
                return "None"
            name = item.get("name", "Unknown")
            return f"{name} ({tier.title()})" if tier else name

        # Dynamic combat stats
        stats = calculate_combat_stats(player)

        # Planet info
        current_planet = player.get("current_planet", 1)
        max_planet = player.get("max_unlocked_planet", 1)
        planet_name = (planets.get(str(current_planet), {}) or {}).get("name", f"Planet {current_planet}")

        title_name = player.get("username") or target_user.display_name

        credits_val = int(player.get("Credits", 0) or 0)

        embed = discord.Embed(
            title=f"{title_name}'s Profile",
            color=discord.Color.blue()
        )
        embed.add_field(name="Level", value=str(player.get("level", 1)), inline=True)
        embed.add_field(name="Total XP", value=str(player.get("total_xp", 0)), inline=True)
        
        s = ensure_sector(player)
        if s > 0:
            embed.add_field(name="Sector", value=f"{s}  •  XP Bonus: +{sector_bonus_percent(s):.2f}%", inline=False)

        embed.add_field(name="Scrap", value=str(player.get("Scrap", 0)), inline=True)
        embed.add_field(
            name="Bank",
            value=("Locked" if not bank.get("unlocked") else f"Balance: {bank['balance']:,} • XP Boost: {boost_str}"),
            inline=True
        )

        embed.add_field(
            name="XP Progress",
            value=f"{current_xp}/{next_level_xp} {bar}",
            inline=False
        )

        embed.add_field(
            name="Health",
            value=f"{player.get('health', 0)}/{get_max_health(player)} 🫀",
            inline=True
        )
        embed.add_field(
            name="Oxygen",
            value=f"{player.get('oxygen', 0)}/{get_max_oxygen(player)} 🫁",
            inline=True
        )

        embed.add_field(
            name="Combat Stats",
            value=f"Attack: {stats['attack']} ⚔️\nDefense: {stats['defense']} 🛡️",
            inline=False
        )

        embed.add_field(
            name="Equipped",
            value=f"Weapon: {label(weapon, w_tier)}\nArmor: {label(armor, a_tier)}",
            inline=False
        )

        embed.add_field(
            name="Travel",
            value=f"🌍 Current: **{planet_name}** (ID: {current_planet})\n"
                  f"🚀 Max Unlocked: Planet {max_planet}",
            inline=False
        )

        embed.add_field(
            name="Credits",
            value=f"{credits_val:,} 💰",
            inline=False
        )

        embed.set_footer(text=f"ID: {target_user.id}")
        embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else discord.Embed.Empty)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Profile(bot))