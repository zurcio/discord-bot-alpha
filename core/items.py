from core.shared import load_json

ITEMS_FILE = "data/items.json"

def get_item_by_id(items, item_id):
    for category in items.values():
        if item_id in category:
            return category[item_id]
    return None

def load_items():
    return load_json(ITEMS_FILE)

def iterate_all_items(items_data):
    """Yield (item_id, item_dict) for both flat and category-grouped items.json structures."""
    if not isinstance(items_data, dict):
        return
    # Detect flat (top-level keys are item ids with 'name')
    if all(isinstance(v, dict) and "name" in v for v in items_data.values()):
        for iid, itm in items_data.items():
            yield iid, itm
        return

    # Otherwise assume categories at top level
    for cat, group in items_data.items():
        if isinstance(group, dict):
            for iid, itm in group.items():
                yield iid, itm


def get_item_by_id(items_data, item_id):
    """
    Look for an item in items_data (nested by category) by ID.
    Returns the item dict or None if not found.
    """
    item_id = str(item_id)
    for category in items_data.values():  # consumables, weapons, armor, etc.
        if item_id in category:
            return category[item_id]
    return None


def find_item(items, item_id):
    """Find an item by ID across all categories."""
    item_id = str(item_id)
    for category in items.values():  # consumables, weapons, armor
        if item_id in category:
            return category[item_id]
    return None