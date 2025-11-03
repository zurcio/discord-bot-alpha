# Lootbox rewards driven by data/lootbox.json
import random
from typing import Dict, List, Tuple
from core.shared import load_json
from core.constants import ITEMS_FILE, LOOTBOXES_FILE

def _clamp_qty(low: int, high: int) -> Tuple[int, int]:
    a, b = int(low), int(high)
    if a > b:
        a, b = b, a
    return max(1, a), max(1, b)

def _index_items(items_data: dict) -> tuple[set[str], dict[str, str]]:
    """
    Build:
      - id_set: all canonical item ids across categories
      - name_to_id: lowercased meta['name'] -> canonical id
    """
    id_set: set[str] = set()
    name_to_id: dict[str, str] = {}
    if not isinstance(items_data, dict):
        return id_set, name_to_id
    for cat, table in items_data.items():
        if not isinstance(table, dict):
            continue
        for iid, meta in table.items():
            sid = str(iid)
            id_set.add(sid)
            if isinstance(meta, dict):
                nm = meta.get("name")
                if isinstance(nm, str) and nm.strip():
                    name_to_id.setdefault(nm.strip().lower(), sid)
    return id_set, name_to_id

def _lookup_meta(items_data: dict, item_id: str) -> tuple[str | None, dict | None]:
    """Return (category, meta) for the given canonical item_id, or (None, None)."""
    sid = str(item_id)
    for cat, table in (items_data or {}).items():
        if isinstance(table, dict) and sid in table:
            return cat, table[sid]
    return None, None

def _canon_entry(entry: str, id_set: set[str], name_to_id: dict[str, str]) -> str:
    """
    Resolve a pool entry to a canonical item id:
      - if already an id in items_data -> keep
      - try replacing spaces with underscores
      - try matching by item 'name' (case-insensitive)
      - else return original string (e.g., 'credit')
    """
    s = str(entry).strip()
    if s in id_set:
        return s
    s_us = s.replace(" ", "_")
    if s_us in id_set:
        return s_us
    nm = s.lower()
    if nm in name_to_id:
        return name_to_id[nm]
    return s  # leave as-is (like 'credit')

def _canon_pool(pool: List[str], id_set: set[str], name_to_id: dict[str, str]) -> List[str]:
    return [_canon_entry(x, id_set, name_to_id) for x in (pool or [])]

def _get_pool_for_rarity(tier_cfg: dict, rarity: str) -> List[str]:
    pools = tier_cfg.get("pools", {}) or {}
    return list(pools.get(rarity, []) or [])

def has_valid_lootbox_config(tier: str) -> bool:
    cfg_all = load_json(LOOTBOXES_FILE) or {}
    tcfg = cfg_all.get(str(tier).lower())
    if not tcfg:
        return False
    pools = tcfg.get("pools", {}) or {}
    return any(len(v or []) > 0 for v in pools.values())

def get_lootbox_config_snapshot(tier: str) -> dict:
    cfg_all = load_json(LOOTBOXES_FILE) or {}
    return cfg_all.get(str(tier).lower(), {})

# ---- Planet gating helpers ----
def _player_max_planet(player: dict) -> int:
    try:
        return int(player.get("max_unlocked_planet") or player.get("current_planet") or 1)
    except Exception:
        return 1

def _material_family(item_key: str) -> str:
    k = str(item_key).lower()
    if k.startswith("plasteel"):
        return "plasteel"
    if k in {"circuit", "microchip", "processor", "motherboard", "quantum_computer"}:
        return "circuit"
    if k.startswith("plasma"):
        return "plasma"
    if k.startswith("bio") or "bio_" in k or k in {"biopolymer", "bio_gel", "bio_metal_hybrid", "bio_material_block"}:
        return "biofiber"
    return "unknown"

def _allowed_family_threshold(fam: str) -> int:
    # Plasteel/Circuit: P1+, Plasma: P3+, Biofiber: P5+
    return {
        "plasteel": 1,
        "circuit": 1,
        "plasma": 3,
        "biofiber": 5,
    }.get(fam, 1)

def _is_allowed_for_planet(item_id: str, items_data: dict, max_planet: int) -> bool:
    # Always allow premium currency or unknown strings
    low = str(item_id).lower()
    if low in {"credit", "credits"}:
        return True

    cat, meta = _lookup_meta(items_data, item_id)
    if not meta:
        # Unknown ids: allow (safe default)
        return True

    itype = str(meta.get("type", "")).lower()
    if itype == "lootbox":
        return True  # allow lootbox rewards
    if cat == "drops":
        # Drops have 'planet': [min, max]
        try:
            rng = meta.get("planet") or []
            if isinstance(rng, list) and rng:
                req = int(rng[0])
                return max_planet >= req
        except Exception:
            return True
        return True
    if cat == "materials":
        fam = _material_family(item_id)
        req = _allowed_family_threshold(fam)
        return max_planet >= req
    # Other categories (weapons/armor/etc.) are allowed by default
    return True

def generate_lootbox_rewards(player: dict, box_tier: str, items_data: dict) -> dict[str, int]:
    """
    Each roll yields exactly 1 unit of a chosen item. Total items per open equals the roll count.
    Duplicates aggregate if the same item is picked multiple times.
    Pool entries in the JSON are canonicalized to real item ids before picking.
    Applies planet gating so players cannot receive materials/drops from planets they haven't reached.
    """
    cfg_all = load_json(LOOTBOXES_FILE) or {}
    tcfg = cfg_all.get(str(box_tier).lower())
    if not tcfg:
        return {}

    rolls_low, rolls_high = tcfg.get("rolls", [1, 1])
    rmin, rmax = _clamp_qty(rolls_low, rolls_high)
    picks = random.randint(rmin, rmax)

    rarity_weights = tcfg.get("rarity_weights", {"common": 100})
    rarity_names = list(rarity_weights.keys())
    rarity_vals = list(rarity_weights.values())

    # Canonicalize pools once per call (for all rarities present)
    items_all = items_data or (load_json(ITEMS_FILE) or {})
    id_set, name_to_id = _index_items(items_all)
    pools_canon: Dict[str, List[str]] = {}
    for rar in rarity_names:
        raw = _get_pool_for_rarity(tcfg, rar)
        pools_canon[rar] = _canon_pool(raw, id_set, name_to_id)

    # Planet-gated filtered pools
    max_planet = _player_max_planet(player or {})
    pools_filtered: Dict[str, List[str]] = {}
    for rar, plist in pools_canon.items():
        allowed = [pid for pid in plist if _is_allowed_for_planet(pid, items_all, max_planet)]
        pools_filtered[rar] = allowed

    # Rarity order for fallback
    default_order = ["common", "uncommon", "rare", "mythic", "legendary"]
    order = [r for r in default_order if r in rarity_names] + [r for r in rarity_names if r not in default_order]

    rewards: Dict[str, int] = {}

    for _ in range(picks):
        # roll rarity by weights
        chosen = random.choices(rarity_names, weights=rarity_vals, k=1)[0]
        pool = pools_filtered.get(chosen, [])

        if not pool:
            # walk to nearest non-empty rarity pool
            if chosen in order:
                idx = order.index(chosen)
            else:
                # if not in order, just pick any non-empty pool
                non_empty = next((pools_filtered[r] for r in order if pools_filtered.get(r)), [])
                pool = non_empty
            if not pool:
                # search neighbors
                for delta in (1, -1, 2, -2, 3, -3, 4, -4):
                    j = (idx + delta) if 'idx' in locals() else None
                    if j is None or j < 0 or j >= len(order):
                        continue
                    alt = pools_filtered.get(order[j], [])
                    if alt:
                        pool = alt
                        break

        if not pool:
            # No valid items available at this rarity after gating; skip this roll
            continue

        chosen_id = random.choice(pool)
        rewards[chosen_id] = rewards.get(chosen_id, 0) + 1

    return rewards