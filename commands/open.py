# ====== OPEN LOOTBOX COMMAND ======
import discord
from discord.ext import commands

from core.shared import load_json
from core.constants import ITEMS_FILE
from core.items import get_item_by_id
from core.guards import require_no_lock, set_lock, clear_lock
from core.players import load_profile, save_profile
from systems.lootboxes import generate_lootbox_rewards, has_valid_lootbox_config
# NEW: Boxer XP award without needing ctx.player
from core.skills_hooks import award_player_skill

TIER_MAP = {
    "c": "common", "common": "common",
    "u": "uncommon", "uncommon": "uncommon",
    "r": "rare", "rare": "rare",
    "m": "mythic", "mythic": "mythic",
    "l": "legendary", "legendary": "legendary",
    # NEW TIERS
    "s": "solar", "solar": "solar",
    "g": "galactic", "galactic": "galactic",
    "ul": "universal", "universal": "universal",
}

# NEW: Boxer XP per lootbox opened (per box, by tier)
BOXER_XP_PER_BOX = {
    "common": 2,
    "uncommon": 5,
    "rare": 12,
    "mythic": 30,
    "legendary": 75,
    "solar": 150,
    "galactic": 300,
    "universal": 600,
}


SHOP_FILE = "data/shop.json"

def _normalize_inventory(inv: dict) -> dict:
    out = {}
    if isinstance(inv, dict):
        for k, v in inv.items():
            try:
                qty = int(v)
            except Exception:
                qty = 0
            if qty > 0:
                out[str(k)] = qty
    return out

def _get_inv(profile: dict) -> dict:
    inv = _normalize_inventory(profile.get("inventory", {}) or {})
    profile["inventory"] = inv
    return inv

def _candidate_lootbox_ids(items_data: dict, tier_key: str) -> list[tuple[str, str]]:
    cands: list[tuple[str, str]] = []
    loot_cat = (items_data.get("lootboxes") or {})
    if isinstance(loot_cat, dict):
        for iid, meta in loot_cat.items():
            if isinstance(meta, dict) and str(meta.get("tier", "")).lower() == tier_key:
                cands.append((str(iid), str(meta.get("name") or f"{tier_key.title()} Lootbox")))
    try:
        shop = load_json(SHOP_FILE) or {}
        loot = (shop.get("lootbox") or {})
        entry = loot.get(tier_key) or {}
        sid = entry.get("item_id")
        if sid:
            cands.append((str(sid), str(entry.get("name") or f"{tier_key.title()} Lootbox")))
    except Exception:
        pass
    fallback = {
        "common": ("300", "Common Lootbox"),
        "uncommon": ("301", "Uncommon Lootbox"),
        "rare": ("302", "Rare Lootbox"),
        "mythic": ("303", "Mythic Lootbox"),
        "legendary": ("304", "Legendary Lootbox"),
        # NEW FALLBACK IDS
        "solar": ("305", "Solar Lootbox"),
        "galactic": ("306", "Galactic Lootbox"),
        "universal": ("307", "Universal Lootbox"),
    }.get(tier_key)
    if fallback and fallback not in cands:
        cands.append(fallback)
    seen = set()
    dedup = []
    for iid, nm in cands:
        if iid not in seen:
            seen.add(iid)
            dedup.append((iid, nm))
    return dedup

def _resolve_lootbox_id_in_inventory(items_data: dict, inv: dict, tier_key: str) -> tuple[str, str]:
    inv_keys = set(inv.keys())
    cands = _candidate_lootbox_ids(items_data, tier_key)
    for iid, nm in cands:
        if iid in inv_keys:
            return iid, nm
    loot_cat = (items_data.get("lootboxes") or {})
    if isinstance(loot_cat, dict):
        for k in inv_keys:
            meta = loot_cat.get(k)
            if isinstance(meta, dict) and str(meta.get("tier", "")).lower() == tier_key:
                return str(k), str(meta.get("name") or f"{tier_key.title()} Lootbox")
    return (cands[0] if cands else (tier_key, f"{tier_key.title()} Lootbox"))

def _apply_delta(inv: dict, delta: dict[str, int]) -> None:
    for iid, d in delta.items():
        sid = str(iid)
        cur = int(inv.get(sid, 0) or 0)
        newv = cur + int(d)
        if newv <= 0:
            inv.pop(sid, None)
        else:
            inv[sid] = newv

class OpenCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="open")
    @require_no_lock()
    async def open_lootbox(self, ctx, tier: str, amount: str = "1"):
        items_data = load_json(ITEMS_FILE) or {}

        tier_key = TIER_MAP.get(str(tier).lower().strip())
        if not tier_key:
            await ctx.send(f"{ctx.author.mention}, invalid lootbox type! Try: c/common, u/uncommon, r/rare, m/mythic, l/legendary.")
            return
        if not has_valid_lootbox_config(tier_key):
            await ctx.send(f"{ctx.author.mention} Lootbox config missing for '{tier_key}'.")
            return

        uid = str(ctx.author.id)
        set_lock(uid, lock_type="lootbox_open", allowed=set(), note=f"open {tier_key}")
        try:
            prof = load_profile(uid) or {}
            inv = _get_inv(prof)

            lb_id, lb_name = _resolve_lootbox_id_in_inventory(items_data, inv, tier_key)
            owned = int(inv.get(lb_id, 0) or 0)
            if owned <= 0:
                await ctx.send(f"{ctx.author.mention}, you don’t have any {lb_name}s to open!")
                return

            amt = str(amount).strip().lower()
            if amt == "all":
                to_open = owned
            elif amt == "half":
                to_open = max(1, owned // 2)
            else:
                try:
                    to_open = int(amt)
                except ValueError:
                    await ctx.send("Invalid amount! Use a number, 'all', or 'half'.")
                    return
                to_open = max(1, min(to_open, owned))

            # Collect rewards
            aggregated: dict[str, int] = {}
            for _ in range(to_open):
                rewards = generate_lootbox_rewards(prof, tier_key, items_data)
                for item_id, qty in rewards.items():
                    sid = str(item_id)
                    aggregated[sid] = aggregated.get(sid, 0) + int(qty)

            if not aggregated:
                await ctx.send(f"{ctx.author.mention} No items were generated. Your {lb_name}(x{to_open}) was not consumed.")
                return

            # Split out premium currency
            credit_keys = {"credit", "credits"}
            credits_gained = 0
            for k in list(aggregated.keys()):
                if k.lower() in credit_keys:
                    credits_gained += int(aggregated.pop(k) or 0)

            # Single delta: consume boxes, add drops
            delta: dict[str, int] = {lb_id: -to_open}
            for iid, q in aggregated.items():
                delta[iid] = delta.get(iid, 0) + q

            # Apply on latest and persist
            latest = load_profile(uid) or {}
            inv_latest = _get_inv(latest)
            _apply_delta(inv_latest, delta)

            # Enforce exact consumption
            expected_final = max(0, owned - to_open)
            if expected_final > 0:
                inv_latest[lb_id] = expected_final
            else:
                inv_latest.pop(lb_id, None)

            # Apply credits to profile (not inventory)
            if credits_gained > 0:
                latest["Credits"] = int(latest.get("Credits", 0) or 0) + credits_gained

            latest["inventory"] = inv_latest

            # NEW: Award Boxer XP (per box × boxes opened)
            boxer_xp_each = int(BOXER_XP_PER_BOX.get(tier_key, 0))
            boxer_xp_total = boxer_xp_each * to_open
            if boxer_xp_total > 0:
                award_player_skill(latest, "boxer", boxer_xp_total)

            save_profile(uid, latest)

            # Build result embed
            lines = []
            if credits_gained > 0:
                lines.append(f"Credits x{credits_gained}")
            sorted_items = sorted(aggregated.items(), key=lambda kv: (-kv[1], kv[0]))
            max_lines = 25
            for idx, (item_id, qty) in enumerate(sorted_items):
                if idx >= max_lines:
                    break
                meta = get_item_by_id(items_data, item_id)
                name = meta.get("name", item_id) if meta else item_id
                emoji = (meta.get("emoji") or "") if meta else ""
                lines.append(f"{emoji} **{name}** x{qty}")
            if len(sorted_items) > max_lines:
                lines.append(f"...and {len(sorted_items) - max_lines} more items.")

            embed = discord.Embed(
                title=f"🎁 {ctx.author.name} opened {to_open}x {lb_name}!",
                description="\n".join(lines),
                color=discord.Color.gold(),
            )
            # NEW: show Boxer XP note
            footer = f"Lootbox tier: {tier_key.title()}"
            if boxer_xp_total > 0:
                footer += f" • 🥊 Boxer +{boxer_xp_total} XP"
            embed.set_footer(text=footer)
            await ctx.send(embed=embed)

        finally:
            clear_lock(uid)

async def setup(bot):
    await bot.add_cog(OpenCommand(bot))