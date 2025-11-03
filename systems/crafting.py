# systems/crafting.py
from __future__ import annotations
import re
from core.shared import load_json
from core.constants import RECIPES_FILE


def load_recipes():
    return load_json(RECIPES_FILE)

def can_craft(player, recipe_id):
    """Check if player has enough materials to craft."""
    recipes = load_recipes()
    recipe = recipes.get(str(recipe_id))
    if not recipe:
        return False

    inv = player.get("inventory", {})
    for item_id, req_qty in recipe["requires"].items():
        if inv.get(item_id, 0) < req_qty:
            return False
    return True

def craft_item(player, recipe_id):
    """Consume materials and add crafted item to inventory."""
    recipes = load_recipes()
    recipe = recipes.get(str(recipe_id))
    if not recipe:
        return None

    inv = player.get("inventory", {})
    for item_id, req_qty in recipe["requires"].items():
        inv[item_id] -= req_qty

    product_id = recipe["produces"]
    inv[product_id] = inv.get(product_id, 0) + 1
    player["inventory"] = inv
    return recipe

def _norm_key(s: str) -> str:
    s = str(s or "")
    out = []
    last_us = False
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            last_us = False
        else:
            if not last_us:
                out.append("_")
                last_us = True
    res = "".join(out).strip("_")
    return res

# Exact per-item Crafter XP (per product unit)
# Keys supported:
# - numeric product ids ("101", "201", ...)
# - normalized product keys ("plasteel_block", "quantum_computer", ...)
# - normalized product names ("plasteel_blade", "circuit_whip", ...)
_CRAFTER_XP = {
    # Materials — plasteel
    "plasteel_sheet": 1,
    "plasteel_bar": 4,
    "plasteel_beam": 20,
    "plasteel_block": 50,

    # Materials — circuit
    "microchip": 1,
    "processor": 4,
    "motherboard": 20,
    "quantum_computer": 50,

    # Materials — plasma
    "plasma_slag": 2,
    "plasma_charge": 5,
    "plasma_core": 25,
    "plasma_module": 70,

    # Materials — biofiber
    "biopolymer": 3,
    "bio_gel": 8,
    # accept both hyphen and underscore variants
    "bio_metal_hybrid": 30,
    "bio-metal_hybrid": 30,
    "bio_material_block": 80,
    "bio-material_block": 80,

    # Weapons (ids + names)
    "101": 4, "plasteel_blade": 4,
    "102": 6, "circuit_whip": 6,
    "103": 8, "plasma_cutter": 8,
    "104": 10, "bio_blade": 10,
    "105": 12, "floral_flouncer": 12,
    "106": 14, "sharder": 14,
    "107": 16, "scrapper": 16,
    "108": 18, "spline_reticulator": 18,
    "109": 20, "quantum_mechanator": 20,

    # Armor (ids + names)
    "201": 4, "plasteel_spacesuit": 4,
    "202": 6, "circuit_suit": 6,
    "203": 8, "plasma_suit": 8,
    "204": 10, "petal_loincloth": 10,
    "205": 12, "ghillie_suit": 12,
    "206": 14, "quartzite_kevlar": 14,
    "207": 16, "scrapsuit": 16,
    "208": 18, "iridium_overalls": 18,
    "209": 20, "quantum_protectenator": 20,
}

def crafter_xp_for_product(product_key: str | int, product_name: str | None = None) -> int:
    """
    Returns Crafter XP for a single crafted product unit.
    Accepts a product id/key and optional display name as fallbacks.
    """
    # 1) exact id match
    k = str(product_key)
    if k in _CRAFTER_XP:
        return int(_CRAFTER_XP[k])

    # 2) normalized key match
    nk = _norm_key(k)
    if nk in _CRAFTER_XP:
        return int(_CRAFTER_XP[nk])

    # 3) normalized name match
    if product_name:
        nn = _norm_key(product_name)
        if nn in _CRAFTER_XP:
            return int(_CRAFTER_XP[nn])

    # 4) alias fixes for common variants
    aliases = {
        "bio-metal_hybrid": "bio_metal_hybrid",
        "bio-material_block": "bio_material_block",
    }
    if nk in aliases:
        ak = aliases[nk]
        if ak in _CRAFTER_XP:
            return int(_CRAFTER_XP[ak])

    return 0