# core/emoji_helper.py
"""
Helper functions for displaying emojis (both unicode and custom Discord emojis).
Custom emoji format: <:name:id> for static, <a:name:id> for animated
"""

def format_emoji(emoji_value: str | int | None, bot=None) -> str:
    """
    Format an emoji for display. Handles:
    - Unicode emojis (e.g., "📦")
    - Custom emoji IDs (e.g., 1234567890)
    - Custom emoji strings (e.g., "<:plasteel:1234567890>")
    - None or empty values (returns empty string)
    
    Args:
        emoji_value: Unicode emoji, custom emoji ID, or full emoji string
        bot: Discord bot instance (optional, for fetching emoji by ID)
    
    Returns:
        Formatted emoji string ready for Discord display
    """
    if not emoji_value:
        return ""
    
    # Already a formatted custom emoji string
    if isinstance(emoji_value, str):
        if emoji_value.startswith("<") and emoji_value.endswith(">"):
            return emoji_value
        # Try to parse as emoji ID
        try:
            emoji_id = int(emoji_value)
            if bot:
                emoji_obj = bot.get_emoji(emoji_id)
                if emoji_obj:
                    return str(emoji_obj)
            # Fallback to manual format
            return f"<:emoji:{emoji_id}>"
        except (ValueError, TypeError):
            # It's a unicode emoji or name, return as-is
            return emoji_value
    
    # It's an emoji ID (integer)
    if isinstance(emoji_value, int):
        if bot:
            emoji_obj = bot.get_emoji(emoji_value)
            if emoji_obj:
                return str(emoji_obj)
        return f"<:emoji:{emoji_value}>"
    
    return ""


def get_item_emoji(item_data: dict, bot=None) -> str:
    """
    Get the emoji for an item from its data dictionary.
    
    Args:
        item_data: Item dictionary (must contain 'emoji' or 'emoji_id' key)
        bot: Discord bot instance (optional)
    
    Returns:
        Formatted emoji string
    """
    if not item_data:
        return ""
    
    # Check for emoji_id first (custom Discord emoji)
    emoji_id = item_data.get("emoji_id")
    if emoji_id:
        return format_emoji(emoji_id, bot)
    
    # Fall back to emoji field (unicode or custom string)
    emoji = item_data.get("emoji", "")
    return format_emoji(emoji, bot)


def format_item_display(item_name: str, item_data: dict = None, bot=None) -> str:
    """
    Format an item name with its emoji.
    
    Args:
        item_name: The name of the item
        item_data: Item dictionary (optional, for emoji lookup)
        bot: Discord bot instance (optional)
    
    Returns:
        "emoji Name" or just "Name" if no emoji
    """
    if not item_data:
        return item_name
    
    emoji = get_item_emoji(item_data, bot)
    if emoji:
        return f"{emoji} {item_name}"
    return item_name
