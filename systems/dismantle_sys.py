import math
from core.shared import load_json, save_json
from core.constants import ITEMS_FILE
from core.players import save_profile
from core.items import resolve_item_by_name_or_alias, get_inventory_key_for_item
from core.parsing import parse_amount

DISMANTLE_RETURN_RATE = 0.8  # 80% return


def get_material_tiers():
    """Defines dismantle progression order for each material group."""
    return {
        "plasteel": ["plasteel", "plasteel sheet", "plasteel bar", "plasteel beam", "plasteel block"],
        "circuit": ["circuit", "microchip", "processor", "motherboard", "quantum computer"],
        "plasma": ["plasma", "plasma slag", "plasma charge", "plasma core", "plasma module"],
        "biofiber": ["biofiber", "biopolymer", "bio gel", "bio-metal hybrid", "bio-material block"]
    }


def dismantle_item(player, item_name: str, amount_input: int | str | None):
    items_data = load_json(ITEMS_FILE)
    inventory = player.get("inventory", {})

    # Resolve item using alias resolution - search only in materials
    category, item_key, item_data = resolve_item_by_name_or_alias(
        items_data, 
        item_name, 
        category_filter=["materials"]
    )
    
    if not item_data:
        return f" `{item_name}` is not a valid material or cannot be dismantled."
    
    resolved_name = item_data.get("name", item_name)
    material_tiers = get_material_tiers()

    # Find which tier the item belongs to
    found_family, tier_index = None, None
    name_normalized = resolved_name.lower().strip()
    
    for family, tiers in material_tiers.items():
        for i, tier_name in enumerate(tiers):
            if name_normalized == tier_name.lower():
                found_family = family
                tier_index = i
                break
        if found_family:
            break

    if not found_family:
        return f" `{resolved_name}` cannot be dismantled."

    if tier_index == 0:
        return f" `{resolved_name}` is the base material and cannot be dismantled further."

    # Find the actual inventory key - try both formats
    inv_key = get_inventory_key_for_item(resolved_name)
    if inv_key not in inventory:
        # Try with the original key from items.json
        inv_key = item_key
    
    have_qty = inventory.get(inv_key, 0)
    
    # Parse amount with knowledge of available quantity (for "half" calculation)
    if amount_input is None:
        amount = 1
    elif isinstance(amount_input, str):
        parsed = parse_amount(amount_input, max_possible=have_qty)
        if parsed == "all":
            amount = have_qty
        elif parsed is None:
            return f" Invalid amount: `{amount_input}`"
        else:
            amount = parsed
    else:
        amount = amount_input
    
    # Validate amount
    if have_qty < amount:
        return f" You don't have enough `{resolved_name}` to dismantle. You have {have_qty}, need {amount}."
    
    if amount <= 0:
        return f" You need to dismantle at least 1 `{resolved_name}`."

    # Determine what item this dismantles into
    lower_tier_name = material_tiers[found_family][tier_index - 1]
    
    # Resolve the lower tier item to get its proper key
    _, lower_item_key, lower_item_data = resolve_item_by_name_or_alias(
        items_data, 
        lower_tier_name, 
        category_filter=["materials"]
    )
    
    if not lower_item_data:
        # Fallback to generated key
        lower_tier_id = get_inventory_key_for_item(lower_tier_name)
    else:
        lower_tier_id = get_inventory_key_for_item(lower_item_data.get("name", lower_tier_name))

    lower_tier_qty = math.floor(10 * DISMANTLE_RETURN_RATE)  # 10  8 by default

    # Apply transaction
    inventory[inv_key] -= amount
    if inventory[inv_key] <= 0:
        del inventory[inv_key]

    inventory[lower_tier_id] = inventory.get(lower_tier_id, 0) + lower_tier_qty * amount
    player["inventory"] = inventory

    save_profile(player["id"], player)
    
    # Get proper display name for lower tier
    lower_display_name = lower_item_data.get("name", lower_tier_name) if lower_item_data else lower_tier_name
    
    return f" Dismantled **{amount}x {resolved_name}**  **{lower_tier_qty * amount}x {lower_display_name}**"
