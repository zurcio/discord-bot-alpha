from __future__ import annotations
import math
from typing import Dict, Tuple

# Post-100 stepped scaling settings (can be tuned later)
POST100_FACTOR_BASE = 2.0      # F for levels 101–103
POST100_FACTOR_STEP = 0.1      # increase every span
POST100_FACTOR_SPAN = 3        # levels per step (101–103, 104–106, ...)
POST100_FACTOR_CAP = 3.0       # cap for F(L)

# Skills: Bank interest principal cap (only first N Scrap earns interest)
SKILLS_BANK_INTEREST_PRINCIPAL_CAP = 1_000_000_000  # 1B (tweak as needed)


# Boxer extra crates cap (tunable)
BOXER_EXTRA_CAP = 5

SKILLS = ("worker","crafter","tinkerer","trader","boxer","gambler","soldier")

def _skill_node(p: dict, k: str) -> dict:
    s = p.setdefault("skills", {})
    n = s.setdefault(k, {"level": 1, "xp": 0})
    n["level"] = int(n.get("level", 1) or 1)
    n["xp"] = int(n.get("xp", 0) or 0)
    return n

def _base_xp_required(name: str, level: int) -> int:
    """Per-level base requirement (L <= 100)."""
    L = max(1, int(level))
    if name == "worker": base = 100 + L*L
    elif name in ("crafter", "tinkerer"): base = round(300 + 3*L*L)
    elif name == "trader": base = round(400 + 4*L*L)
    elif name == "boxer": base = 100 + L*L
    elif name == "gambler": base = round(50 + 0.5*L*L)
    elif name == "soldier": base = round(500 + 5*L*L)
    else: base = 100 + L*L
    return max(1, base)

# Precompute total XP to reach 100 for each skill (sum of base requirements 1..100)
_TOTAL_TO_100: Dict[str, int] = {}
for _name in SKILLS:
    _TOTAL_TO_100[_name] = sum(_base_xp_required(_name, L) for L in range(1, 101))

def _post100_factor(level: int) -> float:
    """F(L) stepped: 101–103=1.9, 104–106=2.0, 107–109=2.1, ..."""
    L = int(level)
    if L <= 100:
        return 1.0
    steps = max(0, (L - 101) // POST100_FACTOR_SPAN)
    f = POST100_FACTOR_BASE + POST100_FACTOR_STEP * steps
    if POST100_FACTOR_CAP is not None:
        f = min(f, POST100_FACTOR_CAP)
    return f

def xp_required(name: str, level: int) -> int:
    L = max(1, int(level))
    if L <= 100:
        return _base_xp_required(name, L)
    # Post-100 stepped requirement based on total to reach 100
    total100 = _TOTAL_TO_100.get(name, _TOTAL_TO_100["worker"])
    req = int(round(total100 * _post100_factor(L)))
    return max(1, req)

def award_skill_xp(player: dict, name: str, amount: int) -> Tuple[int, int]:
    """Awards skill XP; no leveling past 100 unless overcharged is enabled."""
    name = str(name).lower()
    if name not in SKILLS:
        return (0, 0)
    node = _skill_node(player, name)
    node["xp"] += int(amount)

    levels = 0
    # Disallow leveling >100 unless overcharged
    while True:
        lvl = node["level"]
        req = xp_required(name, lvl)
        if node["xp"] < req:
            break

        # If at 100+ and not overcharged, clamp and stop
        if lvl >= 100 and not is_overcharged(player):
            # keep xp just below threshold to show progress without leveling
            node["xp"] = min(node["xp"], req - 1)
            break

        node["xp"] -= req
        node["level"] = lvl + 1
        levels += 1

    return node["level"], levels

def get_level(player: dict, name: str) -> int:
    return _skill_node(player, name)["level"]

def is_overcharged(player: dict) -> bool:
    return bool(player.get("overcharged", False))

def can_overcharge(player: dict) -> bool:
    s = player.get("skills", {}) or {}
    return all(int((s.get(k) or {}).get("level", 1)) >= 100 for k in SKILLS)

def set_overcharged(player: dict, enabled: bool = True) -> None:
    player["overcharged"] = bool(enabled)

def perks_worker(level: int) -> dict:
    # Cross-material chance applies when you decide; Overcharged can bypass planet gates per notes.
    return {
        "work_tier_weight_mult": 1.0 + 0.5 * min(level, 100) / 100.0,
        "cross_material_chance": min(0.03 * max(0, level - 100), 0.75),
    }

def perks_crafter(level: int) -> dict:
    pct = 0.11 if level >= 100 else 0.0
    if level > 100:
        pct = min((10 + (11 * (level - 100))**0.3) / 100.0, 0.35)
    return {"craft_refund_pct": pct}

def perks_tinkerer(level: int) -> dict:
    high_tier_mult = 1.0 + 0.75 * min(level, 100) / 100.0
    refund = 0.0
    if level > 100:
        # per notes: chance_refund = min(0.02*ln(1.2+(lvl-100)), 0.25)
        refund = min(0.02 * math.log(1.2 + (level - 100)), 0.25)
    return {
        "tinker_high_tier_weight_mult": high_tier_mult,
        "tinker_scrap_refund_chance": refund
    }

def perks_trader(level: int) -> dict:
    # 3x at level 100
    if level <= 100:
        mult = 1 + 2 * (level / 100.0)
    else:
        mult = 3 + 0.03 * (level - 100)  # gentle growth beyond 100
        mult = min(mult, 5.0)           # soft cap (tunable)
    return {"sell_price_mult": mult}

def perks_boxer(level: int) -> dict:
    # Chance multiplier applies multiplicatively to base lootbox drop chance
    drop_mult = 1 + 0.05 * min(level, 100) / 100.0
    extra = 0
    if level > 100:
        # +1 at 101, +2 at 103, +3 at 105, ...
        extra = 1 + max(0, (level - 101) // 2)
        if BOXER_EXTRA_CAP is not None:
            extra = min(extra, BOXER_EXTRA_CAP)
    return {"lootbox_chance_mult": drop_mult, "extra_lootboxes": extra}

def perks_gambler(level: int) -> dict:
    bank_xp_bonus = 1 + 0.015 * min(level, 100) / 100.0
    daily_interest = 0.0
    if level > 100:
        daily_interest = min(0.005 * (level - 100), 0.10)
    return {"bank_xp_mult": bank_xp_bonus, "daily_interest_rate": daily_interest}

def perks_soldier(level: int) -> dict:
    cost_reduction = 0.30 * min(level, 100) / 100.0
    if level > 100:
        cost_reduction = min(0.30 + 0.005 * ((level - 100) // 5), 0.50)
    return {
        "ship_upgrade_cost_reduction": cost_reduction,
        "ship_max_level_bonus": max(0, level - 100)
    }


def compute_perks(player: dict) -> dict:
    return {
        "worker": perks_worker(get_level(player, "worker")),
        "crafter": perks_crafter(get_level(player, "crafter")),
        "tinkerer": perks_tinkerer(get_level(player, "tinkerer")),
        "trader": perks_trader(get_level(player, "trader")),
        "boxer": perks_boxer(get_level(player, "boxer")),
        "gambler": perks_gambler(get_level(player, "gambler")),
        "soldier": perks_soldier(get_level(player, "soldier")),
        "overcharged": is_overcharged(player),
    }