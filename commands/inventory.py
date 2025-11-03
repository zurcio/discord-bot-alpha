import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.constants import ITEMS_FILE
from core.shared import load_json
from core.guards import require_no_lock
from core.players import load_profile

FAMILIES = [
    ("Plasteel", [
        "plasteel", "plasteel sheet", "plasteel bar", "plasteel beam", "plasteel block"
    ]),
    ("Circuit", [
        "circuit", "microchip", "processor", "motherboard", "quantum computer"
    ]),
    ("Plasma", [
        "plasma", "plasma slag", "plasma charge", "plasma core", "plasma module"
    ]),
    ("Biofiber", [
        "biofiber", "biopolymer", "bio gel", "bio-metal hybrid", "bio-material block"
    ]),
]

DROPS_CAT = [
    "Crawler Tail", "Slug Slime", "Orchid Bloom", "Crystal Shard", "Lithium Ion"
]

def _id_by_name(items_map: dict, display_name: str) -> str | None:
    dn = display_name.lower()
    for item_id, data in (items_map or {}).items():
        if str(data.get("name", "")).lower() == dn:
            return item_id
    return None

def _collect_by_type(items_root: dict, inventory: dict, type_names: set[str]) -> list[str]:
    """Collect lines for items whose 'type' is in type_names."""
    lines = []
    for category, items in (items_root or {}).items():
        for item_id, data in (items or {}).items():
            t = str(data.get("type", "")).lower()
            if t in type_names:
                qty = int(inventory.get(item_id, 0))
                if qty > 0:
                    lines.append(f"{data.get('name', item_id)} x{qty}")
    return lines

class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["inv", "i"])
    @requires_profile()
    @require_no_lock()
    async def inventory(self, ctx, member: discord.Member | None = None):
        """View inventory in 3 columns: Materials | Drops&Consumables&Lootboxes | Gear&Warpdrives&Keycards."""
        # Resolve target
        target_user = member or ctx.author
        if member is None:
            player = ctx.player  # already loaded by requires_profile
        else:
            player = load_profile(str(member.id))
            if not player:
                await ctx.send(f"{target_user.mention} doesn't have a profile yet.")
                return

        inv = {k: v for k, v in (player.get("inventory") or {}).items() if int(v) > 0}
        if not inv:
            if target_user.id == ctx.author.id:
                await ctx.send(f"{ctx.author.mention}, your inventory is empty!")
            else:
                await ctx.send(f"{target_user.mention} has an empty inventory.")
            return

        items = load_json(ITEMS_FILE) or {}
        mats = items.get("materials", {}) or {}
        drops = items.get("drops", {}) or {}

        # Column 1: Materials (grouped by family, then other materials)
        col1_lines = []
        used_mat_ids = set()

        for fam_name, ordered_names in FAMILIES:
            fam_lines = []
            for disp_name in ordered_names:
                item_id = _id_by_name(mats, disp_name)
                if item_id:
                    qty = int(inv.get(item_id, 0))
                    if qty > 0:
                        fam_lines.append(f"{disp_name} x{qty}")
                        used_mat_ids.add(item_id)
            if fam_lines:
                col1_lines.append(f"**— {fam_name} —**")
                col1_lines.extend(fam_lines)

        # Any other materials not covered by the families
        other_mats = []
        for item_id, data in mats.items():
            if item_id in used_mat_ids:
                continue
            qty = int(inv.get(item_id, 0))
            if qty > 0:
                other_mats.append(f"{data.get('name', item_id)} x{qty}")
        if other_mats:
            col1_lines.append("— Other Materials —")
            col1_lines.extend(sorted(other_mats, key=lambda s: s.lower()))
        col1_text = "\n".join(col1_lines) if col1_lines else "-"

        # Drops (moved to Column 2)
        drop_lines = []
        used_drop_ids = set()

        # First, add drops in the explicit order from DROPS_CAT
        for disp_name in DROPS_CAT:
            item_id = _id_by_name(drops, disp_name)
            if item_id:
                qty = int(inv.get(item_id, 0))
                if qty > 0:
                    drop_lines.append(f"{disp_name} x{qty}")
                    used_drop_ids.add(item_id)

        # Then, include any remaining drops (not listed in DROPS_CAT), alphabetically
        other_drops = []
        for item_id, data in (drops or {}).items():
            if item_id in used_drop_ids:
                continue
            qty = int(inv.get(item_id, 0))
            if qty > 0:
                other_drops.append(f"{data.get('name', item_id)} x{qty}")

        if not drop_lines and not other_drops:
            # Fallback: items tagged as drop by type when not under the drops category
            typed = _collect_by_type(items, inv, {"drop", "enemy_drop"})
            drop_lines.extend(sorted(typed, key=lambda s: s.lower()))
        else:
            drop_lines.extend(sorted(other_drops, key=lambda s: s.lower()))

        # Column 2: Drops, then Consumables, then Lootboxes
        consumable_lines = _collect_by_type(items, inv, {"consumable", "potion", "food"})
        lootbox_lines = _collect_by_type(items, inv, {"lootbox", "crate"})

        col2_parts = []
        if drop_lines:
            col2_parts.append("**— Drops —**")
            col2_parts.extend(drop_lines)
        if consumable_lines:
            col2_parts.append("**— Consumables —**")
            col2_parts.extend(sorted(consumable_lines, key=lambda s: s.lower()))
        if lootbox_lines:
            col2_parts.append("**— Lootboxes —**")
            col2_parts.extend(sorted(lootbox_lines, key=lambda s: s.lower()))
        col2_text = "\n".join(col2_parts) if col2_parts else "-"

        # Column 3: Gear & Warpdrives & Keycards
        gear_lines = _collect_by_type(items, inv, {"weapon", "armor", "gear"})
        warp_lines = _collect_by_type(items, inv, {"warpdrive", "key_item"})
        key_lines = _collect_by_type(items, inv, {"keycard", "key"})

        col3_parts = []
        if gear_lines:
            col3_parts.append("**— Gear —**")
            col3_parts.extend(sorted(gear_lines, key=lambda s: s.lower()))
        if warp_lines:
            col3_parts.append("**— Warpdrives —**")
            col3_parts.extend(sorted(warp_lines, key=lambda s: s.lower()))
        if key_lines:
            col3_parts.append("**— Keycards —**")
            col3_parts.extend(sorted(key_lines, key=lambda s: s.lower()))
        col3_text = "\n".join(col3_parts) if col3_parts else "-"

        # Build embed with three inline fields (columns)
        embed = discord.Embed(
            title=f"{target_user.name}'s Inventory",
            color=discord.Color.gold(),
        )
        embed.add_field(name="🪵 Materials", value=col1_text[:1024] or "-", inline=True)
        embed.add_field(name="💧 Drops, 🍖 Consumables & 🎁 Lootboxes", value=col2_text[:1024] or "-", inline=True)
        embed.add_field(name="⚙️ Gear, 🚀 Warpdrives \n & 🗝️ Keycards", value=col3_text[:1024] or "-", inline=True)

        # In case any column overflows 1024 chars, truncate and hint
        for field in embed.fields:
            if len(field.value) >= 1024:
                field.value = field.value[:1010] + "\n…"

        embed.set_footer(text=f"ID: {target_user.id} • Unique items: {len(inv)}")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Inventory(bot))