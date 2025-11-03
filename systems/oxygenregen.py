import time
from core.constants import ITEMS_FILE
from core.shared import load_json
from core.utils import get_max_health, get_max_oxygen
from core.items import get_item_by_id


def apply_oxygen_regen(player):
    """Apply passive oxygen regeneration based on armor and active Oxygen Tank."""
    now = int(time.time())
    last_regen = player.get("last_regen", now)
    elapsed = now - last_regen

    if elapsed < 60:
        return player  # not enough time has passed

    # How many minutes passed
    minutes = elapsed // 60
    player["last_regen"] = last_regen + minutes * 60

    equipped = player.get("equipped", {})
    armor_id = equipped.get("armor")
    items = load_json(ITEMS_FILE)

    if not armor_id:
        return player  # no armor
    armor = get_item_by_id(items, armor_id)
    if not armor:
        return player

    regen_per_minute = armor.get("oxygen_regen", 0)
    efficiency = armor.get("oxygen_efficiency", 1.0)
    if regen_per_minute <= 0:
        return player

    # Ensure active_tank is valid
    active_tank = player.get("active_tank")
    if not active_tank or active_tank.get("remaining", 0) <= 0:
        # Try to load a fresh Oxygen Tank from inventory
        oxygen_tank_id = "1"
        inventory = player.get("inventory", {})
        if inventory.get(oxygen_tank_id, 0) > 0:
            tank_item = get_item_by_id(items, oxygen_tank_id)
            if not tank_item:
                return player  # item not defined
            player["active_tank"] = {
                "id": oxygen_tank_id,
                "remaining": tank_item.get("value", 50)
            }
            inventory[oxygen_tank_id] -= 1
            player["inventory"] = inventory
        else:
            return player  # no tanks available
        active_tank = player["active_tank"]

    # Oxygen regen process
    total_regen = regen_per_minute * minutes
    max_oxygen = get_max_oxygen(player)
    current_oxygen = player.get("oxygen", 0)

    for _ in range(total_regen):
        if current_oxygen >= max_oxygen:
            break
        if active_tank["remaining"] <= 0:
            # Tank is empty -> clear it so a new one is loaded next tick
            player["active_tank"] = None
            break
        # Apply regen tick
        current_oxygen += 1
        active_tank["remaining"] -= 1 / efficiency

    player["oxygen"] = min(current_oxygen, max_oxygen)
    return player
