import discord
import asyncio
from discord.ext import commands
from core.decorators import requires_profile
from core.guards import require_no_lock
from core.guards import set_lock, clear_lock  # for atomic p2p commit
from core.players import save_profile, load_profile
from core.shared import load_json
from core.constants import ITEMS_FILE
from core.quest_progress import update_quest_progress_for_trade


# Trade IDs and their mappings (1:1 exchange)
TRADE_MAP = {
    "A": ("plasteel", "circuit"),
    "B": ("circuit", "plasteel"),
    "C": ("plasteel", "plasma"),
    "D": ("plasma", "plasteel"),
    "E": ("plasteel", "biofiber"),
    "F": ("biofiber", "plasteel"),
}
# Inverse pairs for player-to-player trade
OPPOSITE_ID = {"A": "B", "B": "A", "C": "D", "D": "C", "E": "F", "F": "E"}

# Planet requirements per trade ID
TRADE_REQUIREMENTS = {
    "C": 3, "D": 3,  # unlock at Planet 3
    "E": 5, "F": 5,  # unlock at Planet 5
}

SPACE_MERCHANT = "Space Merchant"

def _resolve_item_key_and_name(items_data: dict, wanted_name: str) -> tuple[str, str]:
    """
    Find the item id and display name for a given canonical name (e.g., 'plasteel').
    Scans items.json categories for a matching name (case-insensitive).
    Falls back to using the given name as the inventory key.
    """
    wn = (wanted_name or "").strip().lower()
    if not isinstance(items_data, dict):
        return wn, wanted_name.capitalize()
    for cat, items in items_data.items():
        if not isinstance(items, dict):
            continue
        for iid, meta in items.items():
            nm = (meta.get("name") or "").strip().lower()
            if nm == wn:
                return str(iid), meta.get("name", wanted_name.capitalize())
    # Fallback: use the given string as key
    return wn, wanted_name.capitalize()

def _format_trade_lines(items_data: dict, player_planet: int | None = None) -> str:
    lines = []
    for tid, (src, dst) in TRADE_MAP.items():
        _, src_name = _resolve_item_key_and_name(items_data, src)
        _, dst_name = _resolve_item_key_and_name(items_data, dst)
        suffix = ""
        req = TRADE_REQUIREMENTS.get(tid)
        if player_planet is not None and req and player_planet < req:
            suffix = f" (Locked: reach Planet {req})"
        lines.append(f"{tid}: {src_name} → {dst_name}{suffix}")
    return "\n".join(lines)

class Trade(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="trade")
    @requires_profile()
    @require_no_lock()
    async def trade(self, ctx, trade_id: str = None, amount: str = None, *rest):
        """
        Trade first-tier materials.
        Usage:
          • !trade                → show Space Merchant menu
          • !trade [ID] [amt]    → merchant trade (A-F)
          • !trade [ID] [amt] @User → player-to-player trade (inverse applied to the tagged player)
        """
        player = ctx.player
        items_data = load_json(ITEMS_FILE) or {}
        player_planet = int(player.get("current_planet") or player.get("max_unlocked_planet", 1))

        # No args: show menu
        if not trade_id:
            embed = discord.Embed(
                title=f"🛰️ {SPACE_MERCHANT} — Trade Menu",
                description="Trade first-tier materials at a 1:1 rate.",
                color=discord.Color.blurple()
            )
            embed.add_field(
                name="Available Trades",
                value=_format_trade_lines(items_data, player_planet),
                inline=False
            )
            embed.add_field(
                name="Usage",
                value="!trade [ID] [number/half/all]\n"
                      "Player trade: `!trade [ID] [number/half/all] @User`",
                inline=False
            )
            await ctx.send(embed=embed)
            return

        tid = (trade_id or "").strip().upper()
        if tid not in TRADE_MAP:
            await ctx.send(f"{ctx.author.mention} Invalid trade ID. Use `!trade` to see available trades.")
            return

        # Parse amount: number / half / all
        # Note: we may clamp for player-to-player based on both inventories later
        inv_self = player.get("inventory", {}) or {}
        src_key_name, dst_key_name = TRADE_MAP[tid]
        src_key, src_name = _resolve_item_key_and_name(items_data, src_key_name)
        dst_key, dst_name = _resolve_item_key_and_name(items_data, dst_key_name)
        owned_self = int(inv_self.get(src_key, 0) or 0)

        trade_qty = 1
        if amount:
            amt = str(amount).strip().lower()
            if amt == "all":
                trade_qty = owned_self
            elif amt == "half":
                trade_qty = max(1, owned_self // 2)
            else:
                try:
                    trade_qty = int(amt)
                except ValueError:
                    trade_qty = 1

        # Check if a user was mentioned for player-to-player trade
        ally = ctx.message.mentions[0] if ctx.message.mentions else None
        if ally and ally.id == ctx.author.id:
            ally = None  # ignore self-mention

        # Planet gate for the initiator (apply even for P2P)
        req = TRADE_REQUIREMENTS.get(tid)
        if req and player_planet < req:
            await ctx.send(f"{ctx.author.mention} Trade {tid} is locked. Reach Planet {req} to use this trade.")
            return

        if not ally:
            # Space Merchant trade (existing behavior)
            if owned_self <= 0:
                await ctx.send(f"{ctx.author.mention} You don’t have any {src_name} to trade.")
                return
            trade_qty = max(1, min(trade_qty, owned_self))

            # Apply trade (1:1)
            inv_self[src_key] = owned_self - trade_qty
            if inv_self[src_key] <= 0:
                inv_self.pop(src_key, None)
            inv_self[dst_key] = int(inv_self.get(dst_key, 0) or 0) + trade_qty
            player["inventory"] = inv_self

            # Quest: only merchant trades count
            update_quest_progress_for_trade(player)

            save_profile(ctx.author.id, player)
            await ctx.send(f"🤝 {SPACE_MERCHANT}: Traded {trade_qty}x {src_name} → {dst_name} for {ctx.author.mention}.")
            return

        # ===== Player-to-Player Trade =====
        # Load ally
        ally_profile = load_profile(str(ally.id)) or load_profile(ally.id)
        if not ally_profile:
            await ctx.send(f"{ctx.author.mention} {ally.mention} doesn’t have a profile.")
            return

        # Determine ally’s inverse trade
        opp = OPPOSITE_ID.get(tid)
        if not opp:
            await ctx.send(f"{ctx.author.mention} That trade can’t be mirrored for player-to-player.")
            return
        ally_src_key_name, ally_dst_key_name = TRADE_MAP[opp]
        ally_src_key, ally_src_name = _resolve_item_key_and_name(items_data, ally_src_key_name)
        ally_dst_key, ally_dst_name = _resolve_item_key_and_name(items_data, ally_dst_key_name)

        # Planet gate for ally (based on their inverse trade id)
        ally_planet = int(ally_profile.get("current_planet") or ally_profile.get("max_unlocked_planet", 1))
        ally_req = TRADE_REQUIREMENTS.get(opp)
        if ally_req and ally_planet < ally_req:
            await ctx.send(f"{ctx.author.mention} {ally.mention} cannot use the inverse trade ({opp}) until Planet {ally_req}.")
            return

        # Inventories and availability
        inv_ally = ally_profile.get("inventory", {}) or {}
        owned_ally = int(inv_ally.get(ally_src_key, 0) or 0)

        # Final quantity is clamped to what both can afford
        desired_qty = max(1, int(trade_qty or 1))
        final_qty = min(desired_qty, owned_self, owned_ally)
        if final_qty <= 0:
            await ctx.send(
                f"{ctx.author.mention} Trade failed: insufficient materials.\n"
                f"- You have {owned_self} {src_name}\n"
                f"- {ally.display_name} has {owned_ally} {ally_src_name}"
            )
            return

        # Confirm with both players
        yset = {"y", "yes", "ok", "okay", "confirm"}
        nset = {"n", "no", "cancel", "stop"}

        async def ask_yes(user):
            def check(m):
                return m.channel.id == ctx.channel.id and m.author.id == user.id and m.content.lower().strip() in (yset | nset)
            try:
                msg = await self.bot.wait_for("message", timeout=15.0, check=check)
                return msg.content.lower().strip() in yset
            except Exception:
                return None

        embed = discord.Embed(
            title="🤝 Player Trade Confirmation",
            description=(
                f"{ctx.author.mention} offers: {final_qty}x {src_name} → {dst_name}\n"
                f"{ally.mention} offers: {final_qty}x {ally_src_name} → {ally_dst_name}\n\n"
                "Both must reply 'yes' within 15 seconds."
            ),
            color=discord.Color.gold()
        )
        await ctx.send(content=f"{ctx.author.mention} {ally.mention}", embed=embed)
        p_res, a_res = await asyncio.gather(ask_yes(ctx.author), ask_yes(ally))

        if p_res is not True or a_res is not True:
            reason = "timed out" if (p_res is None or a_res is None) else "declined"
            who = []
            if p_res is not True: who.append(ctx.author.mention)
            if a_res is not True: who.append(ally.mention)
            await ctx.send(f"❌ Trade canceled — {', '.join(who)} {reason}.")
            return

        # Perform transfers atomically
        # NEW: Lock both players and reload fresh profiles before mutating
        p_id = str(ctx.author.id)
        a_id = str(ally.id)
        set_lock(p_id, lock_type="trade", allowed=set(), note=f"Trade with {a_id}")
        set_lock(a_id, lock_type="trade", allowed=set(), note=f"Trade with {p_id}")
        try:
            # Reload fresh snapshots to avoid stale ctx.player and ensure latest balances
            player_fresh = load_profile(p_id) or {}
            ally_fresh = load_profile(a_id) or {}

            inv_self = player_fresh.get("inventory", {}) or {}
            inv_ally = ally_fresh.get("inventory", {}) or {}

            # Re-check availability with fresh state
            owned_self = int(inv_self.get(src_key, 0) or 0)
            owned_ally = int(inv_ally.get(ally_src_key, 0) or 0)
            final_qty = min(final_qty, owned_self, owned_ally)
            if final_qty <= 0:
                await ctx.send(
                    f"{ctx.author.mention} Trade failed after recheck: insufficient materials.\n"
                    f"- You now have {owned_self} {src_name}\n"
                    f"- {ally.display_name} now has {owned_ally} {ally_src_name}"
                )
                return

            # Initiator: src_key -> dst_key
            inv_self[src_key] = owned_self - final_qty
            if inv_self[src_key] <= 0:
                inv_self.pop(src_key, None)
            inv_self[dst_key] = int(inv_self.get(dst_key, 0) or 0) + final_qty
            player_fresh["inventory"] = inv_self

            # Ally: ally_src_key -> ally_dst_key
            inv_ally[ally_src_key] = owned_ally - final_qty
            if inv_ally[ally_src_key] <= 0:
                inv_ally.pop(ally_src_key, None)
            inv_ally[ally_dst_key] = int(inv_ally.get(ally_dst_key, 0) or 0) + final_qty
            ally_fresh["inventory"] = inv_ally

            # Save both using string IDs
            save_profile(p_id, player_fresh)
            save_profile(a_id, ally_fresh)

            await ctx.send(
                f"✅ Trade complete: {ctx.author.mention} ⇄ {ally.mention}\n"
                f"- {ctx.author.display_name}: {final_qty}x {src_name} → {dst_name}\n"
                f"- {ally.display_name}: {final_qty}x {ally_src_name} → {ally_dst_name}"
            )
        finally:
            clear_lock(p_id)
            clear_lock(a_id)

async def setup(bot):
    await bot.add_cog(Trade(bot))