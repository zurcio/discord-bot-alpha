from __future__ import annotations
from typing import Dict

def ensure_sector(player: Dict) -> int:
    """
    Ensure sector fields exist. Sector 0 by default (no bonuses).
    """
    if not isinstance(player, dict):
        return 0
    if "sector" not in player or not isinstance(player.get("sector"), int):
        player["sector"] = 0
    return int(player["sector"])

def set_sector(player: Dict, value: int) -> None:
    player["sector"] = max(0, int(value))

def sector_bonus_percent(sector: int) -> float:
    """
    Triangular-like growth per spec:
      bonus_percent = ((99 + s) * s) / 2
    Interpreted as percent. Sector 0 => 0%. Sector 1 => +50%. Sector 2 => +101%, etc.
    These boosts are intentionally large at higher sectors.
    """
    s = max(0, int(sector))
    return ((99 + s) * s) / 2.0

def sector_bonus_multiplier(sector: int) -> float:
    """
    Returns multiplicative factor for XP and other percentage-based bonuses.
    """
    return 1.0 + sector_bonus_percent(sector) / 100.0

def format_sector_bonuses(sector: int) -> str:
    pct = sector_bonus_percent(sector)
    # Same percent applies to XP, enemy drop chance, extra Work items, and global probabilities (per design)
    return (
        f"• Sector: {sector}\n"
        f"• XP Gain: +{pct:.2f}%\n"
        f"• Enemy Drop Chance: +{pct:.2f}%\n"
        f"• Work Items Yield: +{pct:.2f}%\n"
        f"• Global Probabilities: +{pct:.2f}%"
    )