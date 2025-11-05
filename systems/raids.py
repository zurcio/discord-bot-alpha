# systems/raids.py
import json, os, time, math, random
from typing import Dict, Any, Tuple, List
from core.constants import RAIDS_FILE

def _ensure_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)

def _save_json(path: str, data: Any):
    _ensure_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def load_state() -> Dict[str, Any]:
    state = _load_json(RAIDS_FILE) or {}
    # Shape
    state.setdefault("battery", {"progress": 0, "target": 1000, "last_update": int(time.time()), "contributors": {}})
    state.setdefault("active", None)  # or dict with boss
    state.setdefault("history", [])
    return state

def save_state(state: Dict[str, Any]):
    _save_json(RAIDS_FILE, state)

# Tuning
BATTERY_TARGET_BASE = 1000         # base units to fill 100%
BATTERY_PER_EVENT = {              # suggested contributions; hook from commands later
    "scan": 6,
    "work_scavenge": 5,
    "work_hack": 5,
    "work_extract": 5,
    "work_harvest": 5,
    "research": 8,
    "explore": 10,
}
BATTERY_DECAY_PER_HOUR = 0         # optional passive decay (0 = none)

RAID_DURATION_SECONDS = 48 * 3600  # 48h
# Boss HP scales with active player count
def boss_hp_for_active(active_players: int) -> int:
    # 250k per active tester, minimum 3 testers baseline
    n = max(3, int(active_players or 0))
    return int(250_000 * n)

# Damage and support
BASE_DAMAGE_PER_OXY = 150.0
TIER_DAMAGE_BONUS = 0.05    # +5% per tier above 1
LEVEL_DAMAGE_BONUS = 0.01   # +1% per ship level
SUPPORT_COST_PER_MIN = 1000 # Scrap per minute funded
SUPPORT_BONUS_PER_MIN = 0.05 # +5% group damage per funded minute
SUPPORT_MAX_MINUTES_STACK = 30
GROUP_BUFF_CAP = 2.0        # max x2.0 group buff multiplier

# Rewards (simple, safe defaults)
BASE_REWARD_POOL_SCRAP = 50_000    # shared proportionally by contribution
CONSOLATION_POOL_FRACTION = 0.10   # if fail, pay 10% of pool

def _now() -> int:
    return int(time.time())

def _get_group_buff_mult(active: Dict[str, Any]) -> float:
    buffs: List[Dict[str, Any]] = active.get("buffs", [])
    now = _now()
    total = 0.0
    for b in buffs:
        if b.get("expires_at", 0) > now:
            total += float(b.get("mult", 0.0))
    return float(min(GROUP_BUFF_CAP, 1.0 + max(0.0, total)))

def _recalc_battery_target(state: Dict[str, Any], active_player_count: int | None = None):
    bat = state["battery"]
    if active_player_count is None:
        # rough: number of unique contributors in last 48h
        contribs = bat.get("contributors", {})
        cutoff = _now() - 48*3600
        active_player_count = sum(1 for v in contribs.values() if int(v.get("last_ts", 0)) >= cutoff)
        if active_player_count < 3:
            active_player_count = 3
    bat["target"] = max(100, int(BATTERY_TARGET_BASE * active_player_count))

def battery_percent(state: Dict[str, Any]) -> int:
    bat = state["battery"]
    target = max(1, int(bat.get("target", 1000)))
    prog = int(bat.get("progress", 0))
    return int(min(100, math.floor(100.0 * prog / target)))

def charge_battery(state: Dict[str, Any], user_id: str, event_key: str, amount: int | None = None) -> int:
    """
    Add charge to the raid battery. Returns new percent (0..100).
    """
    bat = state["battery"]
    # optional decay
    if BATTERY_DECAY_PER_HOUR > 0:
        last = int(bat.get("last_update", _now()))
        hours = max(0, (_now() - last) // 3600)
        if hours > 0 and bat.get("progress", 0) > 0:
            bat["progress"] = max(0, int(bat["progress"] - BATTERY_DECAY_PER_HOUR * hours))
    add = int(amount if amount is not None else BATTERY_PER_EVENT.get(event_key, 0))
    if add <= 0:
        return battery_percent(state)
    bat["progress"] = int(bat.get("progress", 0)) + add
    bat["last_update"] = _now()
    # record contributor
    c = bat.setdefault("contributors", {})
    ent = c.setdefault(str(user_id), {"total": 0, "last_ts": 0})
    ent["total"] = int(ent.get("total", 0)) + add
    ent["last_ts"] = _now()
    # dynamic target
    _recalc_battery_target(state, None)
    return battery_percent(state)

def can_open(state: Dict[str, Any]) -> bool:
    return state.get("active") is None and battery_percent(state) >= 100

def open_raid(state: Dict[str, Any], boss_name: str | None = None, active_players_hint: int | None = None):
    if state.get("active") is not None:
        return False
    _recalc_battery_target(state, active_players_hint)
    # derive active players
    bat = state["battery"]
    contribs = bat.get("contributors", {})
    cutoff = _now() - 48*3600
    active_players = sum(1 for v in contribs.values() if int(v.get("last_ts", 0)) >= cutoff) or (active_players_hint or 3)
    hp = boss_hp_for_active(active_players)
    state["active"] = {
        "raid_id": f"rb_{_now()}_{random.randint(100,999)}",
        "boss_name": boss_name or "World Eater",
        "hp": hp,
        "hp_max": hp,
        "started_at": _now(),
        "ends_at": _now() + RAID_DURATION_SECONDS,
        "contributors": {},   # uid -> {"damage": int, "actions": int, "last_ts": int}
        "buffs": [],          # [{uid, mult, expires_at, note}]
        "reward_pool": BASE_REWARD_POOL_SCRAP,
        "opened_from_battery": True,
    }
    # Reset battery for next cycle
    bat["progress"] = 0
    bat["last_update"] = _now()
    return True

def is_active(state: Dict[str, Any]) -> bool:
    act = state.get("active")
    if not act:
        return False
    if _now() >= int(act.get("ends_at", 0)):
        return False
    if int(act.get("hp", 0)) <= 0:
        return False
    return True

def get_status(state: Dict[str, Any]) -> Dict[str, Any]:
    bp = battery_percent(state)
    act = state.get("active")
    status = {"battery_percent": bp, "active": False}
    if act:
        status["active"] = True
        status["boss_name"] = act.get("boss_name")
        status["hp"] = int(act.get("hp", 0))
        status["hp_max"] = int(act.get("hp_max", 1))
        status["ends_at"] = int(act.get("ends_at", 0))
        status["group_buff_mult"] = _get_group_buff_mult(act)
        # top 5
        contribs = act.get("contributors", {})
        top = sorted(contribs.items(), key=lambda kv: -int(kv[1].get("damage", 0)))[:5]
        status["top5"] = [(uid, int(e.get("damage", 0))) for uid, e in top]
    return status

def _record_damage(active: Dict[str, Any], uid: str, dmg: int):
    c = active.setdefault("contributors", {})
    e = c.setdefault(str(uid), {"damage": 0, "actions": 0, "last_ts": 0})
    e["damage"] = int(e.get("damage", 0)) + int(max(0, dmg))
    e["actions"] = int(e.get("actions", 0)) + 1
    e["last_ts"] = _now()

def attack(state: Dict[str, Any], uid: str, ship_tier: int, ship_level: int, sector_mult: float, oxygen_spent: int) -> Tuple[int, int, float]:
    """
    Returns (damage_dealt, boss_hp_after, group_buff_mult)
    """
    act = state.get("active")
    if not act or not is_active(state):
        return (0, 0 if act is None else int(act.get("hp", 0)), 1.0)

    oxygen = max(1, int(oxygen_spent))
    tier_bonus = 1.0 + max(0, ship_tier - 1) * TIER_DAMAGE_BONUS
    level_bonus = 1.0 + max(0, ship_level) * LEVEL_DAMAGE_BONUS
    group_mult = _get_group_buff_mult(act)

    dmg = int(math.floor(BASE_DAMAGE_PER_OXY * oxygen * tier_bonus * level_bonus * max(0.1, float(sector_mult)) * group_mult))
    # apply to boss
    cur = int(act.get("hp", 0))
    new_hp = max(0, cur - max(0, dmg))
    act["hp"] = new_hp
    _record_damage(act, uid, dmg)
    return (dmg, new_hp, group_mult)

def add_support(state: Dict[str, Any], uid: str, minutes: int, note: str = "") -> Tuple[float, int]:
    """
    Add a timed group buff. Returns (added_mult, expires_at)
    """
    act = state.get("active")
    if not act or not is_active(state):
        return (0.0, 0)
    mins = int(max(1, min(SUPPORT_MAX_MINUTES_STACK, minutes)))
    mult = float(min(GROUP_BUFF_CAP, mins * SUPPORT_BONUS_PER_MIN))
    expires = _now() + mins * 60
    act.setdefault("buffs", []).append({
        "uid": str(uid),
        "mult": mult,
        "expires_at": expires,
        "note": note or f"Supplied for {mins} min",
    })
    return (mult, expires)

def _payout(active: Dict[str, Any]) -> Dict[str, int]:
    """
    Compute payouts (Scrap) by uid.
    """
    contribs = active.get("contributors", {})
    total = sum(int(v.get("damage", 0)) for v in contribs.values())
    if total <= 0:
        return {}
    pool = int(active.get("reward_pool", BASE_REWARD_POOL_SCRAP))
    payouts: Dict[str, int] = {}
    for uid, ent in contribs.items():
        share = int(ent.get("damage", 0)) / float(total)
        amt = int(math.floor(pool * share))
        if amt > 0:
            payouts[str(uid)] = amt
    return payouts

def maybe_finalize(state: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    If raid ended (hp==0 or time over), produce a result summary and archive.
    Returns summary or None if still running.
    """
    act = state.get("active")
    if not act:
        return None
    ended = False
    reason = ""
    if int(act.get("hp", 0)) <= 0:
        ended = True
        reason = "defeated"
    elif _now() >= int(act.get("ends_at", 0)):
        ended = True
        reason = "expired"

    if not ended:
        return None

    success = (reason == "defeated")
    # compute payouts
    if success:
        payouts = _payout(act)
    else:
        # consolation pool: 10%
        pool = int(max(0, int(act.get("reward_pool", BASE_REWARD_POOL_SCRAP)) * CONSOLATION_POOL_FRACTION))
        act2 = dict(act)
        act2["reward_pool"] = pool
        payouts = _payout(act2)

    summary = {
        "raid_id": act.get("raid_id"),
        "boss_name": act.get("boss_name"),
        "hp_max": int(act.get("hp_max", 0)),
        "duration": int(max(0, _now() - int(act.get("started_at", _now())))),
        "reason": reason,
        "success": success,
        "payouts": payouts,  # uid -> scrap
        "top": sorted(((uid, int(e.get("damage", 0))) for uid, e in act.get("contributors", {}).items()), key=lambda kv: -kv[1])[:10],
        "ended_at": _now(),
    }
    # archive and clear active
    hist = state.setdefault("history", [])
    hist.append(summary)
    state["active"] = None
    return summary
