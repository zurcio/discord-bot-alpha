import re
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.shared import load_json
from core.constants import CRAFTING_FILE, ITEMS_FILE
from core.players import save_profile
from core.guards import set_lock, clear_lock, require_no_lock
from core.quest_progress import update_quest_progress_for_crafting, craft_progress_line_if_applicable
from math import floor
from core.skills_hooks import crafter_effects, award_skill
from systems.crafting import crafter_xp_for_product


def _norm_key(s: str) -> str:
    """Normalize a material key for tolerant matching (case/space/hyphen/underscore)."""
    s = str(s or "")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")

def _build_inv_index(inv: dict[str, int]) -> dict[str, str]:
    """
    Build a normalized lookup map of inventory keys so that:
    - 'Warpdrive MK10', 'warpdrive-mk10', 'warpdrive_mk10' all match the same requirement.
    """
    idx: dict[str, str] = {}
    for k in (inv or {}).keys():
        nk = _norm_key(k)
        if nk not in idx:
            idx[nk] = k
    return idx


class Craft(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="craft", aliases=["make", "cr"])
    @requires_profile()
    @require_no_lock()
    async def craft(self, ctx, *, item_and_amount: str = None):
        """
        Craft items using the crafting.json recipes.
        Usage:
        !craft <item_name>
        !craft <item_name> <amount>
        !craft <item_name> all
        """
        player = ctx.player
        crafting_data = load_json(CRAFTING_FILE).get("recipes", {})
        items_data = load_json(ITEMS_FILE)

        if not item_and_amount:
            await ctx.send(f"{ctx.author.mention} ❌ You must specify an item to craft. Example: `!craft Plasteel Sheet 2`.")
            return

        # --- Split into item name + amount ---
        parts = item_and_amount.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            item_name, amount = parts[0], int(parts[1])
        elif len(parts) == 2 and parts[1].lower() == "all":
            item_name, amount = parts[0], "all"
        else:
            item_name, amount = item_and_amount, 1

        item_name = item_name.lower().strip()

        # --- Find recipe by key, name, or alias ---
        recipe_key, recipe = None, None
        for key, r in crafting_data.items():
            names = [str(key).lower()]
            if "name" in r:
                names.append(str(r["name"]).lower())
            names.extend([str(a).lower() for a in r.get("aliases", [])])
            if item_name in names:
                recipe_key, recipe = key, r
                break

        if not recipe:
            await ctx.send(f"{ctx.author.mention} ❌ Unknown recipe: `{item_name}`")
            return

        # --- Level check ---
        player_level = int(player.get("level", 1) or 1)
        level_req = int(recipe.get("level_req", 0) or 0)
        if player_level < level_req:
            await ctx.send(f"⚠️ You need to be **Level {level_req}** to craft {recipe.get('name', recipe_key)}. (Your level: {player_level})")
            return

        inventory = player.get("inventory", {}) or {}
        inv_index = _build_inv_index(inventory)

        # Helper to get available qty for a required key (supports Scrap and tolerant key matching)
        def available_for(req_key: str) -> int:
            if str(req_key).lower() == "scrap":
                return int(player.get("Scrap", 0) or 0)
            # exact then normalized fallback
            if req_key in inventory:
                return int(inventory.get(req_key, 0) or 0)
            nk = _norm_key(req_key)
            actual = inv_index.get(nk)
            if actual is not None:
                return int(inventory.get(actual, 0) or 0)
            return 0

        # Resolve the actual inventory key we will deduct from (once per required key)
        def resolve_actual_key(req_key: str) -> str | None:
            if str(req_key).lower() == "scrap":
                return None
            if req_key in inventory:
                return req_key
            nk = _norm_key(req_key)
            return inv_index.get(nk)

        # --- Determine craft amount ---
        if isinstance(amount, str) and amount.lower() == "all":
            max_craft = float("inf")
            for mat_id, qty_needed in recipe["materials"].items():
                have = available_for(mat_id)
                max_craft = min(max_craft, have // int(qty_needed))
            amount_to_craft = int(max_craft) if max_craft != float("inf") and max_craft > 0 else 0
            if amount_to_craft == 0:
                await ctx.send(f"{ctx.author.mention} ❌ You don’t have enough materials to craft any {recipe.get('name', recipe_key)}.")
                return
        else:
            if isinstance(amount, int):
                amount_to_craft = max(1, min(100, amount))
            else:
                await ctx.send(f"{ctx.author.mention} ❌ Invalid amount: {amount}")
                return

        # --- Check materials (includes enemy drops and scrap as currency) ---
        for mat_id, qty_needed in recipe["materials"].items():
            need = int(qty_needed) * amount_to_craft
            have = available_for(mat_id)
            if have < need:
                pretty = mat_id.replace("_", " ").title() if mat_id.lower() != "scrap" else "Scrap"
                await ctx.send(f"{ctx.author.mention} ❌ Not enough `{pretty}` to craft {amount_to_craft}x {recipe.get('name', recipe_key)}.")
                return

        # Track total used amounts for refund calculation
        used: dict[str, int] = {}

        # --- Deduct materials ---
        for mat_id, qty_needed in recipe["materials"].items():
            total_need = int(qty_needed) * amount_to_craft
            used[str(mat_id)] = total_need
            if str(mat_id).lower() == "scrap":
                player["Scrap"] = int(player.get("Scrap", 0) or 0) - total_need
                if player["Scrap"] < 0:
                    player["Scrap"] = 0
            else:
                actual_key = resolve_actual_key(mat_id)
                if not actual_key:
                    # Should not happen due to earlier check, but guard anyway
                    await ctx.send(f"{ctx.author.mention} ❌ Missing `{mat_id}` in your inventory.")
                    return
                inventory[actual_key] = int(inventory.get(actual_key, 0) or 0) - total_need
                if inventory[actual_key] <= 0:
                    inventory.pop(actual_key, None)

        # --- Apply Crafter refund perk (deterministic floor(qty_used * pct)) ---
        effects = crafter_effects(player)
        refund_pct = float(effects.get("craft_refund_pct", 0.0))
        refunded_summary: list[str] = []
        if refund_pct > 0:
            for mat_id, qty_used in used.items():
                if qty_used <= 0:
                    continue
                give_back = int(floor(qty_used * refund_pct))
                if give_back <= 0:
                    continue
                if mat_id.lower() == "scrap":
                    player["Scrap"] = int(player.get("Scrap", 0) or 0) + give_back
                    pretty = "Scrap"
                else:
                    # Return to the normalized key actually used if present; otherwise to mat_id
                    actual_key = resolve_actual_key(mat_id) or mat_id
                    inventory[actual_key] = int(inventory.get(actual_key, 0) or 0) + give_back
                    pretty = actual_key.replace("_", " ").title()
                refunded_summary.append(f"{pretty} x{give_back}")

        # --- Add crafted items ---
        output_id = str(recipe_key)  # item id or material key
        output_qty = int(recipe.get("output", 1)) * amount_to_craft
        inventory[output_id] = int(inventory.get(output_id, 0) or 0) + output_qty
        player["inventory"] = inventory

        # Update craft quest progress (if active and matches)
        quest_completed = update_quest_progress_for_crafting(player, str(output_id), int(output_qty))

        # --- Award Crafter skill XP (per product unit, times quantity crafted) ---
        per_item_xp = crafter_xp_for_product(output_id, recipe.get("name"))
        total_xp = per_item_xp * output_qty
        new_lvl, ups = award_skill(ctx, "crafter", total_xp) if total_xp > 0 else (0, 0)

        # Persist profile
        save_profile(ctx.author.id, player)

        # Build message
        extras = []
        if refunded_summary:
            extras.append(f"Refunded: {', '.join(refunded_summary)}")
        if total_xp > 0:
            extras.append(f"Crafter +{total_xp} XP" + (f" (L{new_lvl} +{ups})" if ups > 0 else ""))
        # Append quest progress line if this craft advanced an active craft quest
        qline = craft_progress_line_if_applicable(player, str(output_id))
        if qline:
            extras.append(qline)
        tail = " • " + " • ".join(extras) if extras else ""
        await ctx.send(f"{ctx.author.mention} ✅ Crafted **{amount_to_craft}x {recipe.get('name', recipe_key)}** (x{output_qty} output)!{tail}")

async def setup(bot):
    await bot.add_cog(Craft(bot))
