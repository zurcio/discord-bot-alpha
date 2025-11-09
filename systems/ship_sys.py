from __future__ import annotations
import math
import random
from typing import Dict, Optional, Tuple
from core.skills_hooks import perks_for  


SHIP_TYPES = ("frigate", "monitor", "dreadnought", "freighter", "outrider")  # attack, defense, hp, scrap, tinker
MAX_TIER = 10  # mk1..mk10
MAX_LEVEL = 100

# Tier-up table (base duo probabilities and max attempts per current tier)
TIER_UP_TABLE: Dict[int, Tuple[float, int]] = {
    1: (1.00, 1),
    2: (0.50, 2),
    3: (0.25, 5),
    4: (0.10, 12),
    5: (0.05, 24),
    6: (0.02, 60),
    7: (0.01, 120),
    8: (0.0033, 364),
    9: (0.001, 1200),
    10: (0.0, 0),
}

# Cost tuning constants (adjust to taste)
BASE_UPGRADE_COST = 8000         # global base
TIER_SCALE_STEP = 0.18           # per-tier multiplier step
CUBIC_COEFF_AFTER_50 = 12        # drives L50-100 explosion
ROUND_TO = 500                   # round up for nicer numbers


# Solo or different-tier refit penalties
SOLO_PROB_PENALTY = 0.6          # 60% of duo chance if solo
DIFF_TIER_PROB_PENALTY = 0.75    # if allowing mismatched tiers, scale down

def ensure_ship(player: dict) -> dict:
    """Ensure player has a ship container. Does not give a ship unless one already exists."""
    if "ship" not in player or not isinstance(player["ship"], dict):
        player["ship"] = {"owned": False, "tier": 0, "level": 0, "type": None, "attempts": {}}
    else:
        for k, v in {"owned": False, "tier": 0, "level": 0, "type": None}.items():
            if k not in player["ship"]:
                player["ship"][k] = v
        if "attempts" not in player["ship"] or not isinstance(player["ship"]["attempts"], dict):
            player["ship"]["attempts"] = {}
    return player

def grant_starter_ship(player: dict) -> dict:
    """Give the starter ship (mk1, lvl 1, no type)."""
    ensure_ship(player)
    player["ship"]["owned"] = True
    player["ship"]["tier"] = 1
    player["ship"]["level"] = 1
    player["ship"]["type"] = None
    return player

def mk_name(tier: int) -> str:
    return f"mk{max(1, min(MAX_TIER, int(tier or 1)))}"

def has_ship(player: dict) -> bool:
    return bool(player.get("ship", {}).get("owned"))


# Tunables for cost curve
POLY_DIVISOR = 100_000         # scales curve height; ~16.6B at L100 when tier_mult=1
TIER_MULT_STEP = 0.02          # +2% per tier step (mk10 ≈ +18%)
ROUND_TO = 100                 # round up for cleaner numbers

def upgrade_cost_for_next_level(tier: int, level: int, ship_skill: float = 0.0) -> Optional[int]:
    """
    Scrap cost to go from `level` → `level+1` at given `tier`, using a smooth polynomial curve:
      cost ≈ ((n^4 * (n^2 + 210n + 2200)) * (500 - i^1.2)) / POLY_DIVISOR
    where n = level, i = ship-related skill (future). Tier slightly scales price.
    Targets (mk1, skill=0): L1→2 ≈ 12 Scrap; L100→101 ≈ 16.6B Scrap (before tier).
    """
    if level >= MAX_LEVEL:
        return None

    n = max(1, int(level))  # cost to go from n → n+1
    # Base polynomial shape with gentle early cost and steep late cost
    base = (n**4) * (n**2 + 210*n + 2200)

    # Skill term (future). Keep a minimum floor so it never hits 0.
    skill_term = max(50.0, 500.0 - float(ship_skill) ** 1.2)

    # Tier scaling (small impact, keeps mk10 within same order of magnitude)
    t_mult = 1.0 + TIER_MULT_STEP * max(0, int(tier) - 1)

    raw = (base * skill_term) / POLY_DIVISOR
    cost = raw * t_mult

    # Round up to nearest step
    if ROUND_TO and ROUND_TO > 1:
        cost = math.ceil(cost / ROUND_TO) * ROUND_TO

    return max(1, int(cost))


def type_boost_percent(tier: int, level: int) -> float:
    """
    Returns decimal (e.g., 0.012 = +1.2%) based on tier+level.
    - Level 1 base by tier: mk1 0.10% .. mk10 0.28% (0.001..0.0028)
    - Level 100 target scale: mk1 ~1.00% (x10), mk10 ~28.00% (x100)
    Use non-linear curve favoring higher tiers.
    """
    base_lvl1 = 0.001 + 0.0002 * max(0, tier - 1)  # mk1=0.001..mk10=0.0028
    target_scale = 10 + (tier - 1) * ((100 - 10) / 9.0)  # mk1→10x .. mk10→100x
    x = max(0.0, min(1.0, (level - 1) / 99.0))
    curve = x ** 1.6  # non-linear; slow early, fast later
    scale = 1.0 + (target_scale - 1.0) * curve
    return base_lvl1 * scale  # final percent as decimal

def derive_ship_effects(player: dict) -> dict:
    """
    Derive all ship effects/multipliers for gameplay.
    Returns keys:
      rewards_mult, supply_crate_mult, drop_chance_mult, crew_chance_mult,
      keycard_override (bool), life_support (bool),
      double_drops (bool), double_supply_crates (bool),
      type_boost: {"stat": <one of attack/defense/hp/scrap/tinker>, "value": decimal}
    """
    ensure_ship(player)
    ship = player["ship"]
    if not ship.get("owned"):
        return {
            "rewards_mult": 1.0, "supply_crate_mult": 1.0, "drop_chance_mult": 1.0, "crew_chance_mult": 1.0,
            "keycard_override": False, "life_support": False,
            "double_drops": False, "double_supply_crates": False,
            "type_boost": {"stat": None, "value": 0.0},
        }
    tier = int(ship.get("tier", 1))
    level = int(ship.get("level", 1))
    stype = (ship.get("type") or "").lower() or None

    # Baseline progression multipliers
    rewards_mult = 1.0 + 0.25 * (level / 100.0)  # +25% at L100 (mk1+)
    supply_crate_mult = 1.0 + (0.10 + 0.20 * (level / 100.0)) if tier >= 4 else 1.0  # +10..30%
    drop_chance_mult = 1.0 + (0.10 + 0.20 * (level / 100.0)) if tier >= 8 else 1.0  # +10..30%
    crew_chance_mult = 1.0 + (0.05 + 0.15 * (level / 100.0)) if tier >= 7 else 1.0  # +5..20%

    keycard_override = tier >= 6
    life_support = tier >= 5
    double_flag = (tier >= MAX_TIER)  # mk10 → double drops (items and supply crates)

    # Type-specific boost
    boost_val = type_boost_percent(tier, level)  # decimal
    stat_map = {
        "frigate": "attack",
        "monitor": "defense",
        "dreadnought": "hp",
        "freighter": "scrap",
        "outrider": "tinker",
    }
    return {
        "rewards_mult": rewards_mult,
        "supply_crate_mult": supply_crate_mult,
        "drop_chance_mult": drop_chance_mult,
        "crew_chance_mult": crew_chance_mult,
        "keycard_override": keycard_override,
        "life_support": life_support,
        "double_drops": double_flag,
        "double_supply_crates": double_flag,
        "type_boost": {"stat": stat_map.get(stype), "value": boost_val},
    }

def base_tier_up_chance(current_tier: int) -> float:
    return TIER_UP_TABLE.get(current_tier, (0.0, 0))[0]

def max_attempts_for_tier(current_tier: int) -> int:
    return TIER_UP_TABLE.get(current_tier, (0.0, 0))[1]

def can_tier(player: dict) -> bool:
    ensure_ship(player)
    ship = player["ship"]
    return ship.get("owned") and ship.get("tier", 0) < MAX_TIER

def roll_tier_up(
    rng: random.Random,
    current_tier: int,
    duo: bool,
    allow_mismatch: bool,
    same_tier: bool,
) -> bool:
    p = base_tier_up_chance(current_tier)
    if not duo:
        p *= SOLO_PROB_PENALTY
    if allow_mismatch and not same_tier:
        p *= DIFF_TIER_PROB_PENALTY
    return rng.random() < p
