from __future__ import annotations
from typing import Callable, Dict, List, Tuple
from math import prod
from core.shared import load_json
from core.constants import PLANETS_FILE
from core.bank import bank_xp_multiplier
from systems.ship_sys import derive_ship_effects
from core.utils import add_xp
from core.sector import ensure_sector, sector_bonus_multiplier 

# Types
Modifier = Dict  # { scope: 'xp'|'scrap', kind: 'mult'|'add', value: float|int, source: str, note?: str, priority?: int }
Provider = Callable[[Dict, Dict, Dict, List[str]], List[Modifier]]
# provider(player, base, ctx_meta, tags) -> [Modifier...]

# Registry
_providers: List[Provider] = []
_debug_users: set[str] = set()

def register_provider(fn: Provider):
    _providers.append(fn)

def set_rewards_debug(user_id: str, enabled: bool):
    if enabled: _debug_users.add(str(user_id))
    else: _debug_users.discard(str(user_id))

def _collect_modifiers(player: Dict, base: Dict, ctx_meta: Dict, tags: List[str]) -> List[Modifier]:
    mods: List[Modifier] = []
    for p in _providers:
        try:
            mods.extend(p(player, base, ctx_meta, tags) or [])
        except Exception:
            # Fail-safe: ignore bad providers
            pass
    # stable by priority then source
    for m in mods:
        m.setdefault("priority", 100)
    return sorted(mods, key=lambda m: (m["priority"], m.get("source","z")))
    
def _combine(scope: str, mods: List[Modifier]) -> Tuple[float, int, List[str]]:
    mults = [float(m["value"]) for m in mods if m["scope"] == scope and m["kind"] == "mult"]
    adds  = [int(m["value"])   for m in mods if m["scope"] == scope and m["kind"] == "add"]
    m = prod(mults) if mults else 1.0
    a = sum(adds) if adds else 0
    notes = [f"{m['source']}:{m['kind']}×{m['value']}" for m in mods if m["scope"] == scope]
    return m, a, notes

def apply_rewards(player: Dict, base: Dict, ctx_meta: Dict | None = None, tags: List[str] | None = None) -> Dict:
    """
    Base keys supported: xp, scrap, items
      base = { 'xp': int, 'scrap': int, 'items': {item_id: qty} }
    Returns: { 'applied': {'xp': int, 'scrap': int, 'items': {...}}, 'xp_result': add_xp_result, 'trace': str }
    """
    ctx_meta = ctx_meta or {}
    tags = tags or []

    base_xp = int(base.get("xp") or base.get("XP") or 0)
    base_scrap = int(base.get("scrap") or base.get("Scrap") or 0)
    items = dict(base.get("items") or {})

    mods = _collect_modifiers(player, base, ctx_meta, tags)

    xp_mult, xp_add, xp_notes = _combine("xp", mods)
    sc_mult, sc_add, sc_notes = _combine("scrap", mods)

    xp_final = max(0, int(round(base_xp * xp_mult)) + xp_add)
    sc_final = max(0, int(round(base_scrap * sc_mult)) + sc_add)

    # Apply to player
    xp_res = add_xp(player, xp_final)
    player["Scrap"] = int(player.get("Scrap", 0)) + sc_final

    inv = player.get("inventory", {}) or {}
    for iid, q in items.items():
        inv[str(iid)] = int(inv.get(str(iid), 0)) + int(q)
    player["inventory"] = inv

    # Trace (optional)
    trace = ""
    if str(player.get("id")) in _debug_users:
        lines = []
        lines.append(f"Base: XP={base_xp}, Scrap={base_scrap}")
        lines.append(f"XP: mult={xp_mult:.3f} add={xp_add} -> {xp_final} [{'; '.join(xp_notes)}]")
        lines.append(f"Scrap: mult={sc_mult:.3f} add={sc_add} -> {sc_final} [{'; '.join(sc_notes)}]")
        if items:
            lines.append(f"Items: {items}")
        trace = "\n".join(lines)

    return {
        "applied": {"xp": xp_final, "scrap": sc_final, "items": items},
        "xp_result": xp_res,
        "trace": trace,
    }

# ---------------------------
# Built-in providers
# ---------------------------

def bank_provider(player: Dict, base: Dict, ctx_meta: Dict, tags: List[str]) -> List[Modifier]:
    # Bank affects XP only
    m = bank_xp_multiplier(player)
    return [{"scope": "xp", "kind": "mult", "value": m, "source": "bank", "priority": 50}] if m != 1.0 else []

def ship_provider(player: Dict, base: Dict, ctx_meta: Dict, tags: List[str]) -> List[Modifier]:
    eff = derive_ship_effects(player) or {}
    mods: List[Modifier] = []
    r = float(eff.get("rewards_mult", 1.0))
    if r != 1.0:
        mods.append({"scope": "xp", "kind": "mult", "value": r, "source": "ship", "priority": 60})
        mods.append({"scope": "scrap", "kind": "mult", "value": r, "source": "ship", "priority": 60})
    xm = float(eff.get("xp_mult", 1.0))
    if xm != 1.0:
        mods.append({"scope": "xp", "kind": "mult", "value": xm, "source": "ship.xp", "priority": 61})
    sm = float(eff.get("scrap_mult", 1.0))
    if sm != 1.0:
        mods.append({"scope": "scrap", "kind": "mult", "value": sm, "source": "ship.scrap", "priority": 61})
    return mods

def planet_provider(player: Dict, base: Dict, ctx_meta: Dict, tags: List[str]) -> List[Modifier]:
    root = load_json(PLANETS_FILE) or {}
    data = root.get("planets") if isinstance(root.get("planets"), dict) else root
    pid = str(player.get("current_planet") or player.get("max_unlocked_planet", 1))
    p = data.get(pid) or {}
    xm = float(p.get("xp_mult", 1.0))
    sm = float(p.get("scrap_mult", 1.0))
    mods: List[Modifier] = []
    if xm != 1.0:
        mods.append({"scope": "xp", "kind": "mult", "value": xm, "source": f"planet{pid}", "priority": 70})
    if sm != 1.0:
        mods.append({"scope": "scrap", "kind": "mult", "value": sm, "source": f"planet{pid}", "priority": 70})
    return mods

def sector_provider(player: dict, base: dict, ctx_meta: dict, tags: list) -> list:
    """
    Sector affects XP gain multiplicatively. Other per-system effects (drop chance, work items)
    are applied in their respective systems using sector helpers.
    """
    s = ensure_sector(player)
    m = float(sector_bonus_multiplier(s))
    if m != 1.0:
        return [{"scope": "xp", "kind": "mult", "value": m, "source": f"sector{s}", "priority": 55}]
    return []

# Auto-register built-ins
register_provider(bank_provider)
register_provider(sector_provider)
register_provider(ship_provider)
register_provider(planet_provider)