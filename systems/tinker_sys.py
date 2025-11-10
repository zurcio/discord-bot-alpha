import random
from typing import Dict, Tuple
from core.shared import load_json
from core.constants import ITEMS_FILE
from typing import Dict, Tuple
from core.shared import load_json
from systems.ship_sys import derive_ship_effects 
from core.skills_hooks import tinkerer_effects


# Tier → buff multiplier (final_stat = base_stat * (1 + buff))
TINKER_TIERS: Dict[str, float] = {
    "normal": 0.05,
    "good": 0.10,
    "great": 0.15,
    "excellent": 0.20,
    "mythic": 0.25,
    "legendary": 0.30,
    "molecular": 0.35,
    "atomic": 0.40,
    "neutronic": 0.50,
    "protonic": 0.75,
    "quarkic": 1.00,
    "sophonic": 2.00,
    "quantum": 3.00,
}

# Progression brackets by max_unlocked_planet
def bracket_for_planet(p: int) -> str:
    p = int(p or 1)
    if p >= 10:
        return "p10_plus"
    if p >= 7:
        return "p7_9"
    return "p2_6"

# Weights per bracket (sum to 100)
WEIGHTS_BY_BRACKET: Dict[str, Dict[str, float]] = {
    # P2–6: early game; almost no chance at high tiers
    "p2_6": {
        "normal": 30.0, "good": 29.0, "great": 25.0, "excellent": 10.0, "mythic": 4.0,
        "legendary": 1.5, "molecular": 0.3, "atomic": 0.1, "neutronic": 0.05,
        "protonic": 0.03, "quarkic": 0.014, "sophonic": 0.005, "quantum": 0.001,
    },
    # P7–9: mid/late; strong shift to excellent/mythic/legendary; tiny endgame tail
    "p7_9": {
        "normal": 2.0, "good": 3.0, "great": 20.0, "excellent": 28.0, "mythic": 30.0,
        "legendary": 12.0, "molecular": 3.0, "atomic": 1.0, "neutronic": 0.6,
        "protonic": 0.3, "quarkic": 0.08, "sophonic": 0.015, "quantum": 0.005,
    },
    # P10+: endgame; heavy mythic/legendary with real molecular/atomic; topmost still rare
    "p10_plus": {
        "normal": 0.05, "good": 0.2, "great": 4.0, "excellent": 10.0, "mythic": 30.0,
        "legendary": 30.0, "molecular": 18.0, "atomic": 5.0, "neutronic": 2.0,
        "protonic": 0.5, "quarkic": 0.2, "sophonic": 0.03, "quantum": 0.02,
    },
}

def _section_for_planet(p: int) -> int:
    """Return cost section for planet progression: 0 (locked), 1 (P2–6), 2 (P7–9), 3 (P10+)."""
    p = int(p or 1)
    if p >= 10:
        return 3
    if p >= 7:
        return 2
    if p >= 2:
        return 1
    return 0

def tinker_cost_for_planet(p: int, base_cost: int = 150, round_to: int = 50) -> int:
    """
    Compute Scrap cost for Tinker:
      cost = planet * (10^section) * base_cost
    section: 1 for P2–6, 2 for P7–9, 3 for P10+ (0 → locked)
    Rounded up to the nearest `round_to` (default 50) for clean numbers.
    """
    p = int(p or 1)
    section = _section_for_planet(p)
    if section == 0:
        return 0  # locked before P2

    raw = int(p * (10 ** section) * base_cost)
    if round_to and round_to > 1:
        # round up to nearest step
        raw = ((raw + round_to - 1) // round_to) * round_to
    return raw

def _apply_tinker_ship_boost(player: dict, weights: Dict[str, float]) -> Dict[str, float]:
    """
    If ship type = Outrider, bias weights slightly toward rare tiers.
    Keeps sum the same by reducing common tiers proportionally.
    """
    try:
        eff = derive_ship_effects(player)
        tb = eff.get("type_boost", {})
        if tb.get("stat") != "tinker":
            return weights
        boost = float(tb.get("value", 0.0))  # e.g., 0.012 = 1.2%
    except Exception:
        return weights

    if boost <= 0:
        return weights

    tiers = list(weights.keys())
    w = weights.copy()
    # Define bands
    commons = {"normal", "good", "great"}
    rares = {"excellent", "mythic", "legendary", "molecular", "atomic", "neutronic", "protonic", "quarkic", "sophonic", "quantum"}

    inc_factor = 1.0 + min(0.30, boost * 8.0)  # up to +30% to rares
    dec_factor = 1.0 - min(0.20, boost * 5.0)  # up to -20% to commons

    # Apply factors
    rare_gain = 0.0
    common_loss = 0.0
    for t in tiers:
        if t in rares:
            old = w[t]; w[t] = old * inc_factor; rare_gain += (w[t] - old)
        elif t in commons:
            old = w[t]; w[t] = max(0.0, old * dec_factor); common_loss += (old - w[t])

    # Rebalance: if rare gain > common loss, scale back rares
    total = sum(w.values())
    if total <= 0:
        return weights
    # Normalize to original sum
    orig_sum = sum(weights.values()) or 1.0
    norm = orig_sum / total
    for t in tiers:
        w[t] *= norm
    return w

# NEW: Apply Tinkerer skill high-tier weighting (tiers ≥ excellent)
_HIGH_TIERS = {"excellent", "mythic", "legendary", "molecular", "atomic",
               "neutronic", "protonic", "quarkic", "sophonic", "quantum"}

def _apply_tinker_skill_boost(player: dict, weights: Dict[str, float]) -> Dict[str, float]:
    if not player:
        return weights
    try:
        eff = tinkerer_effects(player)
        mult = float(eff.get("tinker_high_tier_weight_mult", 1.0))
    except Exception:
        mult = 1.0
    if mult <= 1.0:
        return weights

    w = dict(weights)
    # Multiply high tiers then normalize to original sum
    orig_sum = sum(weights.values()) or 1.0
    for t in list(w.keys()):
        if t in _HIGH_TIERS:
            w[t] = w[t] * mult
    new_sum = sum(w.values()) or 1.0
    norm = orig_sum / new_sum
    for t in list(w.keys()):
        w[t] *= norm
    return w

def roll_tinker_tier(max_planet: int, rng=None, player: dict = None) -> Tuple[str, float]:
    rng = rng or random
    bracket = bracket_for_planet(max_planet)
    base_weights = WEIGHTS_BY_BRACKET[bracket]
    # Apply ship bias, then skill bias
    weights = _apply_tinker_ship_boost(player, base_weights) if player else base_weights
    weights = _apply_tinker_skill_boost(player, weights) if player else weights
    tiers = list(weights.keys())
    probs = list(weights.values())
    tier = rng.choices(tiers, weights=probs, k=1)[0]
    return tier, TINKER_TIERS[tier]

def apply_tinker(player: dict, slot: str, effective_planet: int | None = None) -> Tuple[bool, str, float, int, str]:
    """
    slot: "weapon" or "armor"
    effective_planet: if provided, overrides player's planet for cost/weights (use 10 when Overcharged)
    Returns (ok, tier, buff, new_stat_value, item_name)
    Deducts Scrap, overwrites previous enhancement on that item.
    """
    slot = slot.lower().strip()
    if slot not in ("weapon", "armor"):
        return False, "", 0.0, 0, ""

    equipped = (player.get("equipped") or {}).get(slot)
    if not equipped:
        return False, "", 0.0, 0, ""

    items = load_json(ITEMS_FILE)
    category = "weapons" if slot == "weapon" else "armor"
    item_data = (items.get(category, {}) or {}).get(str(equipped))
    if not item_data:
        return False, "", 0.0, 0, ""

    max_planet = int(player.get("max_unlocked_planet", 1) or 1)
    p = int(effective_planet) if effective_planet is not None else max_planet

    cost = tinker_cost_for_planet(p)
    if player.get("Scrap", 0) < cost:
        return False, "", 0.0, 0, item_data.get("name", "")

    # Pay cost up front
    player["Scrap"] = player.get("Scrap", 0) - cost

    # Roll result using effective planet
    tier, buff = roll_tinker_tier(p, player=player)

    # Save enhancement keyed by item_id to allow re-equips
    enh = player.get("enhancements", {})
    enh[str(equipped)] = {"tier": tier, "buff": buff}
    player["enhancements"] = enh

    # Compute new displayed stat
    if slot == "weapon":
        base = int(item_data.get("attack", 0) or 0)
    else:
        base = int(item_data.get("defense", 0) or 0)
    new_val = int(round(base * (1.0 + buff)))
    return True, tier, buff, new_val, item_data.get("name", "")