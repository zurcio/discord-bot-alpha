import json, os
from discord.ext import commands
from typing import Optional, Any
from core.items import load_items, get_item_by_id
from systems.ship_sys import derive_ship_effects


def get_max_health(player_or_level):
    """Accept either a player dict or an integer level."""
    if isinstance(player_or_level, dict):
        level = int(player_or_level.get("level", 1))
    else:
        level = int(player_or_level)
    max_hp = 100 + (level * 5)

    base_max_hp = max_hp

    eff = derive_ship_effects(player_or_level)
    tb = eff.get("type_boost", {})
    if tb and tb.get("stat") == "hp":
        base_max_hp = int(round(max_hp * (1.0 + float(tb.get("value", 0.0)))))
    return base_max_hp

def get_max_oxygen(player_or_level):
    """Accept either a player dict or an integer level. Adds equipped armor oxygen_capacity bonus if present."""
    base = 100
    per_level = 5

    if isinstance(player_or_level, dict):
        level = int(player_or_level.get("level", 1))
        bonus = 0
        armor_id = player_or_level.get("equipped", {}).get("armor")
        if armor_id:
            items = load_items()
            armor = get_item_by_id(items, armor_id)
            if armor and "oxygen_capacity" in armor:
                bonus = int(armor["oxygen_capacity"])
        return base + (level * per_level) + bonus
    else:
        level = int(player_or_level)
        return base + (level * per_level)

def add_xp(player: dict, amount: int) -> dict:
    """Add XP, process level-ups, and clamp health/oxygen to new max. Returns info dict."""
    amount = int(max(0, amount))
    if amount == 0:
        return {"leveled_up": False, "levels_gained": 0, "new_level": int(player.get("level", 1) or 1)}

    player["level"] = int(player.get("level", 1) or 1)
    player["xp"] = int(player.get("xp", 0)) + amount
    player["total_xp"] = int(player.get("total_xp", 0)) + amount

    levels_gained = 0
    while player["xp"] >= player["level"] * 100:
        player["xp"] -= player["level"] * 100
        player["level"] += 1
        levels_gained += 1

    # Clamp to new max after potential level-ups
    player["health"] = min(int(player.get("health", get_max_health(player))), get_max_health(player))
    player["oxygen"] = min(int(player.get("oxygen", get_max_oxygen(player))), get_max_oxygen(player))

    return {"leveled_up": levels_gained > 0, "levels_gained": levels_gained, "new_level": player["level"]}


def make_progress_bar(current, total, length=20):
    """Return a text progress bar."""
    filled = int(length * current // total) if total > 0 else 0
    empty = length - filled
    return "█" * filled + "─" * empty

def parse_amount(arg: str | None, available: int) -> int:
    """
    Parse amount string with support for:
    - 'all' - returns available
    - 'half' - returns available // 2
    - Numbers with K/M/B suffixes (e.g., '1.5m', '500k', '2b')
    - Plain numbers (with or without commas)
    
    Returns clamped value between 0 and available.
    """
    if not arg:
        return 0
    
    t = str(arg).lower().strip()
    
    # Special keywords
    if t == "all":
        return int(available)
    if t == "half":
        return max(1, int(available // 2))
    
    # Parse with K/M/B suffixes
    multiplier = 1
    if t.endswith('k'):
        multiplier = 1_000
        t = t[:-1]
    elif t.endswith('m'):
        multiplier = 1_000_000
        t = t[:-1]
    elif t.endswith('b'):
        multiplier = 1_000_000_000
        t = t[:-1]
    
    try:
        # Remove commas and parse as float (to handle decimals like 1.5m)
        n = float(t.replace(",", ""))
        result = int(n * multiplier)
    except (ValueError, Exception):
        return 0
    
    return max(0, min(result, int(available)))

def parse_float_amount(arg: str | None, available: float) -> float:
    """
    Parse float amount string with support for K/M/B suffixes.
    Used for commodity trading where fractional units are allowed.
    
    Returns clamped value between 0.0 and available.
    """
    if not arg:
        return 0.0
    
    t = str(arg).lower().strip()
    
    # Special keywords
    if t == "all":
        return float(available)
    if t == "half":
        return max(0.0, float(available) / 2.0)
    
    # Parse with K/M/B suffixes
    multiplier = 1.0
    if t.endswith('k'):
        multiplier = 1_000.0
        t = t[:-1]
    elif t.endswith('m'):
        multiplier = 1_000_000.0
        t = t[:-1]
    elif t.endswith('b'):
        multiplier = 1_000_000_000.0
        t = t[:-1]
    
    try:
        # Remove commas and parse as float
        n = float(t.replace(",", ""))
        result = n * multiplier
    except (ValueError, Exception):
        return 0.0
    
    return max(0.0, min(result, float(available)))