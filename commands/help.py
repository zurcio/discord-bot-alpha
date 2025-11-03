import discord
from discord.ext import commands
from typing import List, Dict, Any
from core.shared import load_json
from core.decorators import requires_profile
from core.guards import require_no_lock
from core.constants import ITEMS_FILE, SHOP_FILE
try:
    from core.constants import CREDITSHOP_FILE
except ImportError:
    CREDITSHOP_FILE = "data/creditshop.json"

MECHANICS: Dict[str, Dict[str, Any]] = {
    "sector": {
        "title": "Sector Travel",
        "desc": (
            "After defeating Planet 10 and crafting an FTL Drive, you can travel to the next Sector.\n"
            "This resets your level, inventory, gear, Scrap (not bank), and planets, but grants permanent bonuses to XP, drop chance, and work item yields."
        ),
        "usage": "!sector / !sector travel"
    },
    "bossfight": {
        "title": "Bossfights",
        "desc": "Challenge planetary bosses. Requires a keycard. On victory, earn rewards and unlock the next planet.",
        "usage": "!bossfight"
    },
    "work": {
        "title": "Work Commands",
        "desc": "Gather basic materials with short cooldowns. Yields scale by planet and sector.",
        "usage": "!work scavenge | !work hack | !work extract | !work harvest"
    },
    "scan": {
        "title": "Scan",
        "desc": "Fight a random enemy for XP and Scrap. May drop items or lootboxes.",
        "usage": "!scan"
    },
    "explore": {
        "title": "Explore",
        "desc": "Face elite enemies with better rewards. Longer cooldown.",
        "usage": "!explore"
    },
    "research": {
        "title": "Research",
        "desc": "Answer quick questions for XP. Short timer per question.",
        "usage": "!research"
    },
    "quest": {
        "title": "Quests",
        "desc": "Accept a quest and complete its goals for fixed rewards (no multipliers).",
        "usage": "!quest"
    },
    "ship": {
        "title": "Ships",
        "desc": "View and refit your ship. Higher tiers unlock more bonuses; mk10 doubles enemy drops.",
        "usage": "!ship"
    },
    "shop": {
        "title": "Shop",
        "desc": "Buy items with Scrap. Keycard price scales with your current planet.",
        "usage": "!shop / !buy <item> [amount]"
    },
    "creditshop": {
        "title": "Credit Shop",
        "desc": "Spend Credits on persistent items like a Ship Token. These persist through Sector travel.",
        "usage": "!creditshop"
    },
    "bank": {
        "title": "Bank",
        "desc": "Store Scrap safely. Banked Scrap is preserved on Sector travel.",
        "usage": "!bank deposit <amount> / !bank withdraw <amount>"
    },
}

def _collect_commands(ctx: commands.Context) -> List[Dict[str, Any]]:
    entries = []
    for cmd in ctx.bot.commands:
        if cmd.hidden:
            continue
        name = cmd.name
        aliases = getattr(cmd, "aliases", []) or []
        help_text = (cmd.help or "").strip() if getattr(cmd, "help", None) else ""
        desc = help_text if help_text else "No description available."
        entries.append({
            "kind": "command",
            "key": name.lower(),
            "name": f"!{name}",
            "aliases": [a.lower() for a in aliases],
            "desc": desc,
            "usage": f"!{name}",
        })
    return entries

def _collect_items() -> List[Dict[str, Any]]:
    data = load_json(ITEMS_FILE) or {}
    entries = []
    for category, items in (data.items() if isinstance(data, dict) else []):
        if not isinstance(items, dict): 
            continue
        for iid, item in items.items():
            name = item.get("name", str(iid))
            aliases = [a.lower() for a in item.get("aliases", [])]
            desc = item.get("description", "No description available.")
            entries.append({
                "kind": "item",
                "key": name.lower(),
                "name": name,
                "aliases": aliases + [str(iid).lower()],
                "desc": desc,
                "usage": f"Obtain via gameplay or crafting.",
            })
    return entries

def _collect_shop() -> List[Dict[str, Any]]:
    shop = load_json(SHOP_FILE) or {}
    entries = []
    for category, items in (shop.items() if isinstance(shop, dict) else []):
        if not isinstance(items, dict):
            continue
        for iid, entry in items.items():
            nm = entry.get("name") or str(iid)
            desc = entry.get("description", "No description available.")
            entries.append({
                "kind": "shop",
                "key": nm.lower(),
                "name": nm,
                "aliases": [str(iid).lower()],
                "desc": desc,
                "usage": "!shop / !buy <item>",
            })
    return entries

def _collect_creditshop() -> List[Dict[str, Any]]:
    cs = load_json(CREDITSHOP_FILE) or {}
    items = cs.get("items", {}) if isinstance(cs, dict) else {}
    entries = []
    for iid, entry in (items.items() if isinstance(items, dict) else []):
        nm = entry.get("name") or str(iid)
        desc = entry.get("description", "No description available.")
        entries.append({
            "kind": "creditshop",
            "key": nm.lower(),
            "name": nm,
            "aliases": [str(iid).lower()],
            "desc": desc,
            "usage": "!creditshop",
        })
    return entries

def _collect_mechanics() -> List[Dict[str, Any]]:
    entries = []
    for key, meta in MECHANICS.items():
        entries.append({
            "kind": "mechanic",
            "key": key.lower(),
            "name": meta["title"],
            "aliases": [],
            "desc": meta["desc"],
            "usage": meta.get("usage", ""),
        })
    return entries

def _search(entries: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    q = query.lower().strip()
    def score(e):
        name = e["key"]
        aliases = e.get("aliases", [])
        if q == name or q in aliases:
            return 0  # best
        if q in name:
            return 1
        for a in aliases:
            if q in a:
                return 2
        if q in e.get("desc", "").lower():
            return 3
        return 4
    results = sorted(entries, key=score)
    return [r for r in results if score(r) < 4]

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliases=["info"])
    @require_no_lock()
    async def help(self, ctx, *, query: str = None):
        if not query:
            embed = discord.Embed(
                title="ℹ️ Help & Info",
                description=(
                    "Use `!help <thing>` to get info about commands, items, shop entries, or mechanics.\n"
                    "Examples:\n"
                    "• `!help scan`\n"
                    "• `!help keycard`\n"
                    "• `!help sector`\n"
                    "• `!help ship`"
                ),
                color=discord.Color.blurple()
            )
            embed.add_field(name="Tip", value="Most game content has a short description. If something is missing, ping the dev.")
            await ctx.send(embed=embed)
            return

        entries: List[Dict[str, Any]] = []
        entries += _collect_commands(ctx)
        entries += _collect_items()
        entries += _collect_shop()
        entries += _collect_creditshop()
        entries += _collect_mechanics()

        results = _search(entries, query)
        if not results:
            await ctx.send(f"No info found for `{query}`.")
            return

        # Render top 6 results
        top = results[:6]
        embed = discord.Embed(
            title=f"🔎 Results for: {query}",
            color=discord.Color.green()
        )
        for r in top:
            name = r["name"]
            kind = r["kind"].capitalize()
            desc = r.get("desc", "No description available.")
            usage = r.get("usage", "")
            field_val = desc
            if usage:
                field_val += f"\nUsage: {usage}"
            embed.add_field(name=f"{name}  •  {kind}", value=field_val[:1024], inline=False)

        if len(results) > len(top):
            embed.set_footer(text=f"{len(results) - len(top)} more results not shown. Refine your search.")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Help(bot))