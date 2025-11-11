import time
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.players import save_profile
from core.shared import load_json, save_json
from core.guards import require_no_lock
from core.utils import add_xp
from systems.ship_sys import grant_starter_ship, ensure_ship
from core.constants import ITEMS_FILE  
from core.items import get_item_by_id  

CODES_FILE = "data/codes.json"

def _norm(code: str) -> str:
    return (code or "").strip().lower()

def _now() -> int:
    return int(time.time())

def _is_expired(expires_at) -> bool:
    if not expires_at:
        return False
    try:
        return _now() >= int(expires_at)
    except Exception:
        return False

def _apply_rewards(player: dict, rewards: dict) -> list[str]:
    """Apply rewards to player. Returns a list of human-readable lines."""
    lines = []
    inv = player.get("inventory", {}) or {}
    rewards = rewards or {}

    # Load item catalog to resolve names
    items_catalog = load_json(ITEMS_FILE) or {}

    # Reserved keys that are NOT items
    reserved_keys = {"Scrap", "Credits", "xp", "items", "starter_ship"}
    
    scrap = int(rewards.get("Scrap", 0) or 0)
    credits = int(rewards.get("Credits", 0) or 0)
    xp = int(rewards.get("xp", 0) or 0)
    give_starter_ship = bool(rewards.get("starter_ship", False))

    if scrap:
        player["Scrap"] = int(player.get("Scrap", 0)) + scrap
        lines.append(f"+{scrap:,} Scrap")
    if credits:
        player["Credits"] = int(player.get("Credits", 0) or 0) + int(credits)
        lines.append(f"+{int(credits):,} Credits")
    if xp:
        res = add_xp(player, xp)
        msg = f"+{xp:,} XP"
        if res.get("leveled_up"):
            msg += f" (Level {player.get('level', 1)})"
        lines.append(msg)

    # Collect all items from both "items" field and direct item IDs in rewards
    all_items = {}
    
    # Legacy support: items nested in "items" field
    legacy_items = rewards.get("items", {}) or {}
    for item_id, qty in legacy_items.items():
        all_items[str(item_id)] = int(qty or 0)
    
    # New support: item IDs directly in rewards (anything not in reserved_keys)
    for key, value in rewards.items():
        if key not in reserved_keys:
            # This is an item ID
            all_items[str(key)] = int(value or 0)
    
    # Apply all items
    for item_id, qty in all_items.items():
        if qty <= 0:
            continue
        key = str(item_id)
        inv[key] = int(inv.get(key, 0)) + qty
        # Resolve display name
        item_def = get_item_by_id(items_catalog, key)
        if item_def:
            display_name = item_def.get("name", key)
            emoji = item_def.get("emoji", "")
            display = f"{emoji} {display_name}".strip() if emoji else display_name
        else:
            display = f"Item #{key}"
        lines.append(f"+{qty} x {display}")

    player["inventory"] = inv

    if give_starter_ship:
        ensure_ship(player)
        if not player["ship"].get("owned"):
            grant_starter_ship(player)
            lines.append("Starter Ship granted")

    return lines


class RedeemCode(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="code", aliases=["redeem"])
    @requires_profile()
    @require_no_lock()
    async def code(self, ctx, code: str = None):
        """Redeem a reward code set by the game admins."""
        if not code:
            await ctx.send(f"{ctx.author.mention}, usage: `!code <code>`")
            return

        data = load_json(CODES_FILE) or {}
        codes = data.get("codes", {}) or {}

        key = _norm(code)
        cfg = codes.get(key)
        if not cfg:
            await ctx.send("❌ Invalid or unknown code.")
            return

        # Validate code status
        if bool(cfg.get("disabled", False)):
            await ctx.send("❌ This code is disabled.")
            return
        if _is_expired(cfg.get("expires_at")):
            await ctx.send("❌ This code has expired.")
            return

        # Global uses_left: -1 or None = unlimited
        uses_left = cfg.get("uses_left", -1)
        if isinstance(uses_left, int) and uses_left >= 0 and uses_left == 0:
            await ctx.send("❌ This code has reached its redemption limit.")
            return

        # Per-user redemption tracking
        player = ctx.player
        redeemed = player.get("redeemed_codes", {}) or {}
        per_user_limit = int(cfg.get("per_user_limit", 1))
        user_uses = int(redeemed.get(key, 0))
        if per_user_limit > 0 and user_uses >= per_user_limit:
            await ctx.send("❌ You have already redeemed this code.")
            return

        # Apply rewards
        rewards = cfg.get("rewards", {}) or {}
        lines = _apply_rewards(player, rewards)

        # Update per-user and global counters
        redeemed[key] = user_uses + 1
        player["redeemed_codes"] = redeemed

        if isinstance(uses_left, int) and uses_left > 0:
            cfg["uses_left"] = max(0, uses_left - 1)
            codes[key] = cfg
            data["codes"] = codes
            save_json(CODES_FILE, data)

        save_profile(ctx.author.id, player)

        if not lines:
            await ctx.send("✅ Code redeemed.")
        else:
            desc = "\n".join(f"• {line}" for line in lines)
            embed = discord.Embed(
                title="✅ Code redeemed!",
                description=desc,
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(RedeemCode(bot))