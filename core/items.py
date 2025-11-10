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


def resolve_item_by_name_or_alias(items_data, query, category_filter=None):
    """
    Find an item by name or alias across all categories (or filtered categories).
    Returns (category_name, item_key, item_data) or (None, None, None) if not found.
    
    Args:
        items_data: The items.json data structure
        query: The search term (can be name or alias)
        category_filter: Optional list of category names to search within
    """
    query_normalized = query.lower().strip().replace("_", " ").replace("-", " ")
    
    # Determine which categories to search
    categories_to_search = {}
    if category_filter:
        for cat in category_filter:
            if cat in items_data:
                categories_to_search[cat] = items_data[cat]
    else:
        categories_to_search = items_data
    
    # Search through categories
    for category_name, category_items in categories_to_search.items():
        if not isinstance(category_items, dict):
            continue
            
        for item_key, item_data in category_items.items():
            if not isinstance(item_data, dict):
                continue
            
            # Check item name
            item_name = item_data.get("name", "")
            name_normalized = item_name.lower().strip().replace("_", " ").replace("-", " ")
            
            if query_normalized == name_normalized:
                return (category_name, item_key, item_data)
            
            # Check aliases
            aliases = item_data.get("aliases", [])
            for alias in aliases:
                alias_normalized = alias.lower().strip().replace("_", " ").replace("-", " ")
                if query_normalized == alias_normalized:
                    return (category_name, item_key, item_data)
    
    return (None, None, None)


def get_inventory_key_for_item(item_name):
    """
    Convert an item name to its inventory key format (underscores instead of spaces).
    Handles common variations.
    """
    return item_name.lower().strip().replace(" ", "_").replace("-", "_")