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

###############################################
# Raid Type 1 (World Boss + Resource Siege)
# Reworked mechanics (personal batteries + mega weapons)
###############################################

# Personal artillery battery tuning
PERSONAL_TARGET_UNITS = 100              # 100 units = 100% charge
PERSONAL_FULL_DAMAGE_FRAC = 0.005        # 0.5% boss max HP at 100%
PERSONAL_ATTACK_COOLDOWN_SEC = 60 * 60   # 60 minutes cooldown after firing (before charging again)
PERSONAL_CHARGE_COOLDOWN_SEC = 5 * 60    # 5 minutes between charge actions

# Charge conversion (per design spec)
# Personal: 1 unit per 10 material OR per 0.2% total scrap (wallet + bank balance)
PERSONAL_MATERIALS_PER_UNIT = 10
PERSONAL_SCRAP_PERCENT_PER_UNIT = 0.2    # percent of total scrap (wallet+bank)

# Mega weapons: 1 unit per 100 material OR per 0.5% total scrap (wallet + bank balance)
MEGA_TARGET_UNITS = 100                  # Each firing requires 100 units
MEGA_DAMAGE_FRAC = 0.10                  # 10% boss max HP per firing
MEGA_MATERIALS_PER_UNIT = 100
MEGA_SCRAP_PERCENT_PER_UNIT = 0.5        # percent of total scrap (wallet+bank)
MEGA_CHARGE_COOLDOWN_SEC = 60 * 60       # 1 hour cooldown after charging mega-weapon

MEGA_WEAPON_KEYS = {
    "scrap": "ATM Machine",
    "plasteel": "Flak Cannon",
    "circuit": "Chain Vulcan",
    "plasma": "Artillery Beam",
    "biofiber": "Almond Launcher",
}

# Rewards (rank band payouts)
BASE_REWARD_POOL_SCRAP = 50_000    # base pool for successful raid
CONSOLATION_POOL_FRACTION = 0.10   # if fail, pay 10% of pool

# Rank band payout structure (can be tweaked)
# Format: (max_rank, fraction_of_pool)
RANK_BANDS = [
    (1, 0.30),    # Rank 1: 30% of pool
    (3, 0.20),    # Ranks 2-3: 20% each
    (5, 0.10),    # Ranks 4-5: 10% each
    (10, 0.05),   # Ranks 6-10: 5% each
    (999, 0.02),  # Ranks 11+: 2% each
]

def _now() -> int:
    return int(time.time())

def _init_personal_container(active: Dict[str, Any]):
    active.setdefault("personal", {})  # uid -> {progress,target,last_attack_ts,last_charge_ts,total_units}

def _init_mega_container(active: Dict[str, Any]):
    mega = active.setdefault("mega", {})
    for k, name in MEGA_WEAPON_KEYS.items():
        mega.setdefault(k, {"name": name, "progress": 0, "target": MEGA_TARGET_UNITS, "contributors": {}, "last_charge_ts": 0})
    return mega

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
    # Do not charge main battery while a raid is active
    if state.get("active") is not None and is_active(state):
        return battery_percent(state)
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
        "contributors": {},   # uid -> {"damage": int, "actions": int, "last_ts": int, "personal_units": int, "mega_units": int}
        "reward_pool": BASE_REWARD_POOL_SCRAP,
        "opened_from_battery": True,
    }
    _init_personal_container(state["active"])
    _init_mega_container(state["active"])
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
        # Personal battery percent for caller computed elsewhere (not stored here globally)
        # Mega weapon summary
        mega = act.get("mega") or {}
        status["mega"] = {k: {"progress": v.get("progress", 0), "target": v.get("target", MEGA_TARGET_UNITS)} for k, v in mega.items()}
        # top 5
        contribs = act.get("contributors", {})
        top = sorted(contribs.items(), key=lambda kv: -int(kv[1].get("damage", 0)))[:5]
        status["top5"] = [(uid, int(e.get("damage", 0))) for uid, e in top]
    return status

def _record_damage(active: Dict[str, Any], uid: str, dmg: int, personal_units: int = 0, mega_units: int = 0):
    c = active.setdefault("contributors", {})
    e = c.setdefault(str(uid), {"damage": 0, "actions": 0, "last_ts": 0, "personal_units": 0, "mega_units": 0})
    e["damage"] = int(e.get("damage", 0)) + int(max(0, dmg))
    e["actions"] = int(e.get("actions", 0)) + (1 if dmg > 0 else 0)
    e["last_ts"] = _now()
    if personal_units:
        e["personal_units"] = int(e.get("personal_units", 0)) + int(personal_units)
    if mega_units:
        e["mega_units"] = int(e.get("mega_units", 0)) + int(mega_units)

def _get_personal(active: Dict[str, Any], uid: str) -> Dict[str, Any]:
    _init_personal_container(active)
    return active["personal"].setdefault(str(uid), {"progress": 0, "target": PERSONAL_TARGET_UNITS, "last_attack_ts": 0, "last_charge_ts": 0, "total_units": 0})

def personal_percent(b: Dict[str, Any]) -> int:
    tgt = max(1, int(b.get("target", PERSONAL_TARGET_UNITS)))
    prog = int(b.get("progress", 0))
    return int(min(100, math.floor(100.0 * prog / tgt)))

def can_charge_personal(b: Dict[str, Any]) -> Tuple[bool, int]:
    """Check if personal battery can be charged. Returns (can_charge, cooldown_remaining_sec)."""
    # Check attack cooldown (1 hour after firing)
    last_attack = int(b.get("last_attack_ts", 0))
    if last_attack and _now() - last_attack < PERSONAL_ATTACK_COOLDOWN_SEC:
        cd = PERSONAL_ATTACK_COOLDOWN_SEC - (_now() - last_attack)
        return (False, cd)
    # Check charge cooldown (5 min between charges)
    last_charge = int(b.get("last_charge_ts", 0))
    if last_charge and _now() - last_charge < PERSONAL_CHARGE_COOLDOWN_SEC:
        cd = PERSONAL_CHARGE_COOLDOWN_SEC - (_now() - last_charge)
        return (False, cd)
    return (True, 0)

def charge_personal_from_materials(state: Dict[str, Any], uid: str, units: int) -> Tuple[int, int]:
    """Charge personal battery. Returns (percent_after, cooldown_remaining_sec)."""
    act = state.get("active")
    if not act or not is_active(state):
        return (0, 0)
    b = _get_personal(act, uid)
    can_charge, cd = can_charge_personal(b)
    if not can_charge:
        return (personal_percent(b), cd)
    add = max(0, int(units))
    b["progress"] = int(b.get("progress", 0)) + add
    b["total_units"] = int(b.get("total_units", 0)) + add
    b["last_charge_ts"] = _now()
    return (personal_percent(b), 0)

def attack_personal(state: Dict[str, Any], uid: str) -> Tuple[int, int, int, int]:
    """Fire personal artillery. Returns (damage, hp_after, percent_used, cooldown_remaining)."""
    act = state.get("active")
    if not act or not is_active(state):
        return (0, 0 if act is None else int(getattr(act, "hp", 0)), 0, 0)
    b = _get_personal(act, uid)
    pct = personal_percent(b)
    # Cooldown check
    last = int(b.get("last_attack_ts", 0))
    if last and _now() - last < PERSONAL_ATTACK_COOLDOWN_SEC:
        remaining = PERSONAL_ATTACK_COOLDOWN_SEC - (_now() - last)
        return (0, int(act.get("hp", 0)), pct, remaining)
    if pct <= 0:
        return (0, int(act.get("hp", 0)), pct, 0)
    # Damage proportional to percent (linear)
    hp_max = int(act.get("hp_max", 1))
    dmg_full = int(math.floor(hp_max * PERSONAL_FULL_DAMAGE_FRAC))
    dmg = int(math.floor(dmg_full * (pct / 100.0)))
    cur = int(act.get("hp", 0))
    new_hp = max(0, cur - max(0, dmg))
    act["hp"] = new_hp
    # Record damage & reset battery
    units_used = int(b.get("progress", 0))
    _record_damage(act, uid, dmg, personal_units=units_used)
    b["progress"] = 0
    b["last_attack_ts"] = _now()
    return (dmg, new_hp, pct, 0)

def get_personal_status(state: Dict[str, Any], uid: str) -> Tuple[int, int]:
    """Return (percent, cooldown_remaining_sec) for a user's personal battery."""
    act = state.get("active")
    if not act or not is_active(state):
        return (0, 0)
    b = _get_personal(act, uid)
    pct = personal_percent(b)
    last = int(b.get("last_attack_ts", 0))
    cd = 0
    if last and _now() - last < PERSONAL_ATTACK_COOLDOWN_SEC:
        cd = PERSONAL_ATTACK_COOLDOWN_SEC - (_now() - last)
    return (pct, cd)

def mega_percent(entry: Dict[str, Any]) -> int:
    tgt = max(1, int(entry.get("target", MEGA_TARGET_UNITS)))
    prog = int(entry.get("progress", 0))
    return int(min(100, math.floor(100.0 * prog / tgt)))

def charge_mega(state: Dict[str, Any], uid: str, key: str, units: int) -> Tuple[int, bool, int, int]:
    """Charge a mega weapon. Returns (percent_after, fired, damage_if_fired, cooldown_remaining_sec)."""
    act = state.get("active")
    if not act or not is_active(state):
        return (0, False, 0, 0)
    mega = _init_mega_container(act)
    if key not in mega:
        return (0, False, 0, 0)
    entry = mega[key]
    
    # Check cooldown (1 hour after last charge)
    last_charge = int(entry.get("last_charge_ts", 0))
    if last_charge and _now() - last_charge < MEGA_CHARGE_COOLDOWN_SEC:
        cd = MEGA_CHARGE_COOLDOWN_SEC - (_now() - last_charge)
        return (mega_percent(entry), False, 0, cd)
    
    add = max(0, int(units))
    if add <= 0:
        return (mega_percent(entry), False, 0, 0)
    entry["progress"] = int(entry.get("progress", 0)) + add
    entry["last_charge_ts"] = _now()
    
    # Track contributor units for attribution when firing
    contribs = entry.setdefault("contributors", {})
    contribs[str(uid)] = int(contribs.get(str(uid), 0)) + add
    pct = mega_percent(entry)
    fired = False
    damage_done = 0
    if entry["progress"] >= entry.get("target", MEGA_TARGET_UNITS):
        # Fire
        hp_max = int(act.get("hp_max", 1))
        damage_done = int(math.floor(hp_max * MEGA_DAMAGE_FRAC))
        cur = int(act.get("hp", 0))
        act["hp"] = max(0, cur - damage_done)
        fired = True
        # Attribute damage proportionally to contributors
        total_units = sum(int(v) for v in contribs.values()) or 1
        for cid, units_c in contribs.items():
            portion = damage_done * (units_c / total_units)
            _record_damage(act, cid, int(math.floor(portion)), mega_units=units_c)
        # Reset weapon
        entry["progress"] = 0
        entry["contributors"] = {}
        entry["last_charge_ts"] = 0  # Reset cooldown on fire
        pct = mega_percent(entry)
    return (pct, fired, damage_done, 0)

def calculate_scrap_total(profile: Dict[str, Any]) -> int:
    if not isinstance(profile, dict):
        return 0
    wallet = int(profile.get("Scrap", 0) or 0)
    bank_bal = int(((profile.get("bank") or {}).get("balance") or 0))
    return wallet + bank_bal

def convert_to_personal_units(resource_key: str, amount: int, total_scrap: int) -> int:
    if resource_key == "scrap":
        if total_scrap <= 0:
            return 0
        # amount here is scrap spent; each unit requires PERSONAL_SCRAP_PERCENT_PER_UNIT percent of total scrap
        percent = (amount / max(1, total_scrap)) * 100.0
        units = int(math.floor(percent / PERSONAL_SCRAP_PERCENT_PER_UNIT))
        return max(0, units)
    # materials
    units = int(math.floor(amount / PERSONAL_MATERIALS_PER_UNIT))
    return max(0, units)

def convert_to_mega_units(resource_key: str, amount: int, total_scrap: int) -> int:
    if resource_key == "scrap":
        if total_scrap <= 0:
            return 0
        percent = (amount / max(1, total_scrap)) * 100.0
        units = int(math.floor(percent / MEGA_SCRAP_PERCENT_PER_UNIT))
        return max(0, units)
    units = int(math.floor(amount / MEGA_MATERIALS_PER_UNIT))
    return max(0, units)

def _payout(active: Dict[str, Any]) -> Dict[str, int]:
    """
    Compute payouts (Scrap) by uid using rank bands.
    """
    contribs = active.get("contributors", {})
    if not contribs:
        return {}
    
    # Sort by damage descending
    ranked = sorted(contribs.items(), key=lambda kv: -int(kv[1].get("damage", 0)))
    pool = int(active.get("reward_pool", BASE_REWARD_POOL_SCRAP))
    payouts: Dict[str, int] = {}
    
    for rank, (uid, ent) in enumerate(ranked, 1):
        # Find the band for this rank
        reward_frac = 0.0
        for max_rank, frac in RANK_BANDS:
            if rank <= max_rank:
                reward_frac = frac
                break
        
        amt = int(math.floor(pool * reward_frac))
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
        "claimed": [],  # track who has claimed payouts
    }
    # archive and clear active
    hist = state.setdefault("history", [])
    hist.append(summary)
    state["active"] = None
    return summary

def claim_payout(state: Dict[str, Any], uid: str) -> Tuple[int, Dict[str, Any]]:
    """Allow a player to claim their payout from the most recent summary. Returns (amount, summary)."""
    hist = state.get("history", [])
    if not hist:
        return (0, {})
    latest = hist[-1]
    if state.get("active") is not None:  # cannot claim while active raid
        return (0, latest)
    claimed = latest.setdefault("claimed", [])
    if str(uid) in claimed:
        return (0, latest)
    amount = int(latest.get("payouts", {}).get(str(uid), 0))
    if amount > 0:
        claimed.append(str(uid))
    return (amount, latest)

