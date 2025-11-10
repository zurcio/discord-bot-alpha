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
    
    # MIGRATION: Run migration on load to handle structure changes
    _migrate_raid_data(state)
    
    return state

def save_state(state: Dict[str, Any]):
    _save_json(RAIDS_FILE, state)

def _migrate_raid_data(state: Dict[str, Any]):
    """
    Migrate old raid data structures to new format.
    This ensures compatibility when deploying changes to an active raid.
    """
    active = state.get("active")
    if not active:
        return  # No active raid to migrate
    
    # Migrate mega weapon contributors
    mega = active.get("mega", {})
    for weapon_key, weapon_data in mega.items():
        contribs = weapon_data.get("contributors", {})
        for uid, data in list(contribs.items()):
            # Old format: uid -> int (just units count)
            # New format: uid -> {"units": int, "timestamps": []}
            if isinstance(data, int):
                contribs[uid] = {"units": data, "timestamps": []}
            elif isinstance(data, dict):
                # Ensure all required fields exist
                if "units" not in data:
                    data["units"] = 0
                if "timestamps" not in data:
                    data["timestamps"] = []
        
        # Remove deprecated last_charge_ts field
        weapon_data.pop("last_charge_ts", None)
    
    # Migrate personal batteries
    personal = active.get("personal", {})
    for uid, battery in personal.items():
        # Remove deprecated last_charge_ts field
        battery.pop("last_charge_ts", None)
        
        # Initialize attack_cooldown for existing batteries
        if battery.get("last_attack_ts", 0) > 0 and "attack_cooldown" not in battery:
            battery["attack_cooldown"] = PERSONAL_ATTACK_COOLDOWN_SEC

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
PERSONAL_MAX_CHARGE = 200                # Max 200% charge (overcharge allowed)
PERSONAL_FULL_DAMAGE_FRAC = 0.005        # 0.5% boss max HP at 100%
PERSONAL_ATTACK_COOLDOWN_SEC = 60 * 60   # 60 minutes base cooldown after firing

# Charge conversion (per design spec)
# Personal: 1 unit per 0.2% total materials OR per 0.2% total scrap (wallet + bank balance)
PERSONAL_MATERIALS_PERCENT_PER_UNIT = 0.2    # percent of total materials in inventory
PERSONAL_SCRAP_PERCENT_PER_UNIT = 0.2        # percent of total scrap (wallet+bank)

# Mega weapons: 1 unit per 0.5% total materials OR per 0.5% total scrap (wallet + bank balance)
MEGA_TARGET_UNITS = 100                  # Each firing requires 100 units
MEGA_DAMAGE_FRAC = 0.10                  # 10% boss max HP per firing
MEGA_MATERIALS_PERCENT_PER_UNIT = 0.5        # percent of total materials in inventory
MEGA_SCRAP_PERCENT_PER_UNIT = 0.5            # percent of total scrap (wallet+bank)
MEGA_HOURLY_CONTRIBUTION_LIMIT = 10          # Max 10% contribution per player per hour

MEGA_WEAPON_KEYS = {
    "scrap": "ATM Machine",
    "plasteel": "Flak Cannon",
    "circuit": "Chain Vulcan",
    "plasma": "Artillery Beam",
    "biofiber": "Almond Launcher",
}

# Rewards (rank band payouts)
BASE_REWARD_POOL_SCRAP = 500_000_000    # base pool for successful raid
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

# Supply crate rewards by rank band
# Format: {rank_band: {item_id: quantity}}
SUPPLY_CRATE_REWARDS = {
    1: {"305": 1, "304": 3, "303": 5, "302": 10, "301": 20, "300": 30},  # Rank 1: 1 solar, 3 legendary, 5 mythic, 10 rare, 20 uncommon, 30 common
    2: {"304": 2, "303": 5, "302": 10, "301": 15, "300": 20},            # Ranks 2-3: 2 legendary, 5 mythic, 10 rare, 15 uncommon, 20 common
    3: {"304": 1, "303": 3, "302": 5, "301": 10, "300": 15},             # Ranks 4-5: 1 legendary, 3 mythic, 5 rare, 10 uncommon, 15 common
    4: {"303": 3, "302": 5, "301": 10, "300": 15},                       # Ranks 6-10: 3 mythic, 5 rare, 10 uncommon, 15 common
    5: {"303": 1, "302": 3, "301": 5, "300": 10},                        # Ranks 11+: 1 mythic, 3 rare, 5 uncommon, 10 common
}

def _now() -> int:
    return int(time.time())

def _init_personal_container(active: Dict[str, Any]):
    active.setdefault("personal", {})  # uid -> {progress,target,last_attack_ts,last_charge_ts,total_units}

def _init_mega_container(active: Dict[str, Any]):
    mega = active.setdefault("mega", {})
    for k, name in MEGA_WEAPON_KEYS.items():
        # contributors now maps uid -> {"units": int, "timestamps": [list of contribution timestamps]}
        entry = mega.setdefault(k, {"name": name, "progress": 0, "target": MEGA_TARGET_UNITS, "contributors": {}})
        
        # MIGRATION: Convert old contributor format to new format
        contribs = entry.get("contributors", {})
        for uid, data in list(contribs.items()):
            # Old format: uid -> int (just units)
            # New format: uid -> {"units": int, "timestamps": []}
            if isinstance(data, int):
                # Migrate old format
                contribs[uid] = {"units": data, "timestamps": []}
            elif isinstance(data, dict) and "timestamps" not in data:
                # Partial migration - has units but no timestamps
                if "units" not in data:
                    # Very old format stored as dict but without proper structure
                    contribs[uid] = {"units": 0, "timestamps": []}
                else:
                    data.setdefault("timestamps", [])
        
        # Remove old last_charge_ts field if present
        entry.pop("last_charge_ts", None)
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
    Auto-opens raid when battery reaches 100%.
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
    pct = battery_percent(state)
    
    # Auto-open raid when battery hits 100%
    if pct >= 100 and can_open(state):
        open_raid(state, boss_name="World Eater")
    
    return pct

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
    battery = active["personal"].setdefault(str(uid), {"progress": 0, "target": PERSONAL_TARGET_UNITS, "last_attack_ts": 0, "total_units": 0})
    
    # MIGRATION: Remove old last_charge_ts field (no longer used)
    battery.pop("last_charge_ts", None)
    
    # MIGRATION: Initialize attack_cooldown if not present (for existing batteries on cooldown)
    # If they have a last_attack_ts but no attack_cooldown, set default
    if battery.get("last_attack_ts", 0) > 0 and "attack_cooldown" not in battery:
        battery["attack_cooldown"] = PERSONAL_ATTACK_COOLDOWN_SEC  # Default to base cooldown
    
    return battery

def personal_percent(b: Dict[str, Any]) -> int:
    """Calculate personal battery charge percentage (can exceed 100%, max 200%)."""
    tgt = max(1, int(b.get("target", PERSONAL_TARGET_UNITS)))
    prog = int(b.get("progress", 0))
    return int(min(PERSONAL_MAX_CHARGE, math.floor(100.0 * prog / tgt)))

def can_charge_personal(b: Dict[str, Any]) -> Tuple[bool, int]:
    """
    Check if personal battery can be charged. Returns (can_charge, cooldown_remaining_sec).
    Now only checks attack cooldown - no cooldown between charges.
    """
    # Check attack cooldown (base 1 hour after firing, scales with overcharge)
    last_attack = int(b.get("last_attack_ts", 0))
    if last_attack:
        # Get the cooldown that was set when attacking
        attack_cd = int(b.get("attack_cooldown", PERSONAL_ATTACK_COOLDOWN_SEC))
        if _now() - last_attack < attack_cd:
            cd = attack_cd - (_now() - last_attack)
            return (False, cd)
    return (True, 0)

def charge_personal_from_materials(state: Dict[str, Any], uid: str, units: int) -> Tuple[int, int, int]:
    """
    Charge personal battery. Allows overcharge up to 200%.
    Returns (percent_after, cooldown_remaining_sec, units_capped) where units_capped is actual units added.
    """
    act = state.get("active")
    if not act or not is_active(state):
        return (0, 0, 0)
    b = _get_personal(act, uid)
    can_charge, cd = can_charge_personal(b)
    if not can_charge:
        return (personal_percent(b), cd, 0)
    
    add = max(0, int(units))
    current_progress = int(b.get("progress", 0))
    target = int(b.get("target", PERSONAL_TARGET_UNITS))
    max_progress = target * PERSONAL_MAX_CHARGE // 100  # 200% = 200 units
    
    # Cap to max charge
    if current_progress + add > max_progress:
        add = max(0, max_progress - current_progress)
    
    b["progress"] = current_progress + add
    b["total_units"] = int(b.get("total_units", 0)) + add
    return (personal_percent(b), 0, add)

def attack_personal(state: Dict[str, Any], uid: str) -> Tuple[int, int, int, int]:
    """
    Fire personal artillery. Returns (damage, hp_after, percent_used, cooldown_remaining).
    Cooldown scales with overcharge: base 60min at 100%, +50% at 200% (linear scaling).
    """
    act = state.get("active")
    if not act or not is_active(state):
        return (0, 0 if act is None else int(getattr(act, "hp", 0)), 0, 0)
    b = _get_personal(act, uid)
    pct = personal_percent(b)
    # Cooldown check
    last = int(b.get("last_attack_ts", 0))
    if last:
        attack_cd = int(b.get("attack_cooldown", PERSONAL_ATTACK_COOLDOWN_SEC))
        if _now() - last < attack_cd:
            remaining = attack_cd - (_now() - last)
            return (0, int(act.get("hp", 0)), pct, remaining)
    if pct <= 0:
        return (0, int(act.get("hp", 0)), pct, 0)
    
    # Damage proportional to percent (linear, caps at 200%)
    hp_max = int(act.get("hp_max", 1))
    dmg_full = int(math.floor(hp_max * PERSONAL_FULL_DAMAGE_FRAC))
    # Scale damage: 100% = 1.0x, 200% = 2.0x
    dmg = int(math.floor(dmg_full * (pct / 100.0)))
    cur = int(act.get("hp", 0))
    new_hp = max(0, cur - max(0, dmg))
    act["hp"] = new_hp
    
    # Calculate cooldown based on charge level
    # At 100%: base cooldown (60min)
    # At 200%: base + 50% = 90min
    # Linear scaling: cooldown = base * (1 + 0.5 * ((pct - 100) / 100))
    if pct <= 100:
        cooldown = PERSONAL_ATTACK_COOLDOWN_SEC
    else:
        overcharge_factor = (pct - 100) / 100.0  # 0.0 at 100%, 1.0 at 200%
        cooldown = int(PERSONAL_ATTACK_COOLDOWN_SEC * (1 + 0.5 * overcharge_factor))
    
    # Record damage & reset battery
    units_used = int(b.get("progress", 0))
    _record_damage(act, uid, dmg, personal_units=units_used)
    b["progress"] = 0
    b["last_attack_ts"] = _now()
    b["attack_cooldown"] = cooldown  # Store for next cooldown check
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
    if last:
        attack_cd = int(b.get("attack_cooldown", PERSONAL_ATTACK_COOLDOWN_SEC))
        if _now() - last < attack_cd:
            cd = attack_cd - (_now() - last)
    return (pct, cd)

def mega_percent(entry: Dict[str, Any]) -> int:
    tgt = max(1, int(entry.get("target", MEGA_TARGET_UNITS)))
    prog = int(entry.get("progress", 0))
    return int(min(100, math.floor(100.0 * prog / tgt)))

def charge_mega(state: Dict[str, Any], uid: str, key: str, units: int) -> Tuple[int, bool, int, str, int]:
    """
    Charge a mega weapon with 10% per hour rate limiting per player.
    Returns (percent_after, fired, damage_if_fired, rate_limit_msg, units_actually_added).
    """
    act = state.get("active")
    if not act or not is_active(state):
        return (0, False, 0, "", 0)
    mega = _init_mega_container(act)
    if key not in mega:
        return (0, False, 0, "", 0)
    entry = mega[key]
    
    # Get player's contribution history for rate limiting
    contribs = entry.setdefault("contributors", {})
    user_contrib = contribs.setdefault(str(uid), {"units": 0, "timestamps": []})
    
    # Clean up old timestamps (older than 1 hour)
    timestamps = user_contrib.get("timestamps", [])
    one_hour_ago = _now() - 3600
    timestamps = [ts for ts in timestamps if ts > one_hour_ago]
    user_contrib["timestamps"] = timestamps
    
    # Calculate how many units contributed in last hour
    units_last_hour = len(timestamps)  # Each timestamp represents 1 unit contributed
    max_units_per_hour = MEGA_TARGET_UNITS * MEGA_HOURLY_CONTRIBUTION_LIMIT // 100  # 10% of 100 = 10 units
    
    # Check rate limit
    rate_limit_msg = ""
    add = max(0, int(units))
    if add <= 0:
        return (mega_percent(entry), False, 0, "", 0)
    
    # Cap contribution to rate limit
    if units_last_hour >= max_units_per_hour:
        return (mega_percent(entry), False, 0, "⏱️ Rate limit: max 10% per hour already reached. Try again later.", 0)
    
    available_capacity = max_units_per_hour - units_last_hour
    if add > available_capacity:
        add = available_capacity
        rate_limit_msg = f"⚠️ Contribution capped to {add} units (10% per hour limit)."
    
    # Add contribution
    entry["progress"] = int(entry.get("progress", 0)) + add
    
    # Track contribution with timestamps
    for _ in range(add):
        timestamps.append(_now())
    user_contrib["timestamps"] = timestamps
    user_contrib["units"] = int(user_contrib.get("units", 0)) + add
    
    pct = mega_percent(entry)
    fired = False
    damage_done = 0
    
    # Check if weapon fires
    if entry["progress"] >= entry.get("target", MEGA_TARGET_UNITS):
        # Fire
        hp_max = int(act.get("hp_max", 1))
        damage_done = int(math.floor(hp_max * MEGA_DAMAGE_FRAC))
        cur = int(act.get("hp", 0))
        act["hp"] = max(0, cur - damage_done)
        fired = True
        
        # Attribute damage proportionally to contributors
        total_units = sum(int(c.get("units", 0)) for c in contribs.values()) or 1
        for cid, c_data in contribs.items():
            units_c = int(c_data.get("units", 0))
            if units_c > 0:
                portion = damage_done * (units_c / total_units)
                _record_damage(act, cid, int(math.floor(portion)), mega_units=units_c)
        
        # Reset weapon
        entry["progress"] = 0
        entry["contributors"] = {}
        pct = mega_percent(entry)
    
    return (pct, fired, damage_done, rate_limit_msg, add)

def calculate_scrap_total(profile: Dict[str, Any]) -> int:
    """Calculate total scrap (wallet + bank balance)."""
    if not isinstance(profile, dict):
        return 0
    wallet = int(profile.get("Scrap", 0) or 0)
    bank_bal = int(((profile.get("bank") or {}).get("balance") or 0))
    return wallet + bank_bal

def calculate_material_total(profile: Dict[str, Any], material_key: str) -> int:
    """Calculate total of a specific material in inventory."""
    if not isinstance(profile, dict):
        return 0
    inv = profile.get("inventory", {})
    return int(inv.get(material_key, 0) or 0)

def parse_amount(amount_str: str, total_available: int) -> int:
    """
    Parse amount string supporting k/m/b/half/all.
    Returns the parsed integer amount, capped at total_available.
    """
    s = str(amount_str).lower().strip()
    
    # Handle special keywords
    if s in ("all", "max"):
        return total_available
    if s in ("half", "h"):
        return total_available // 2
    
    # Handle numeric with suffix
    multiplier = 1
    if s.endswith('k'):
        multiplier = 1_000
        s = s[:-1]
    elif s.endswith('m'):
        multiplier = 1_000_000
        s = s[:-1]
    elif s.endswith('b'):
        multiplier = 1_000_000_000
        s = s[:-1]
    
    try:
        base = float(s)
        result = int(base * multiplier)
        return min(result, total_available)
    except:
        return 0

def convert_to_personal_units(resource_key: str, amount: int, total_scrap: int, total_materials: int = 0) -> int:
    """
    Convert resource amount to personal battery charge units.
    - Scrap: based on % of total scrap (wallet + bank)
    - Materials: based on % of total materials in inventory
    """
    if resource_key == "scrap":
        if total_scrap <= 0:
            return 0
        # amount here is scrap spent; each unit requires PERSONAL_SCRAP_PERCENT_PER_UNIT percent of total scrap
        percent = (amount / max(1, total_scrap)) * 100.0
        units = int(math.floor(percent / PERSONAL_SCRAP_PERCENT_PER_UNIT))
        return max(0, units)
    # materials
    if total_materials <= 0:
        return 0
    percent = (amount / max(1, total_materials)) * 100.0
    units = int(math.floor(percent / PERSONAL_MATERIALS_PERCENT_PER_UNIT))
    return max(0, units)

def convert_to_mega_units(resource_key: str, amount: int, total_scrap: int, total_materials: int = 0) -> int:
    """
    Convert resource amount to mega weapon charge units.
    - Scrap: based on % of total scrap (wallet + bank)
    - Materials: based on % of total materials in inventory
    """
    if resource_key == "scrap":
        if total_scrap <= 0:
            return 0
        percent = (amount / max(1, total_scrap)) * 100.0
        units = int(math.floor(percent / MEGA_SCRAP_PERCENT_PER_UNIT))
        return max(0, units)
    # materials
    if total_materials <= 0:
        return 0
    percent = (amount / max(1, total_materials)) * 100.0
    units = int(math.floor(percent / MEGA_MATERIALS_PERCENT_PER_UNIT))
    return max(0, units)

def get_charge_preview_personal(resource_key: str, amount: int, total_scrap: int, total_materials: int, current_percent: int) -> Dict[str, Any]:
    """
    Calculate preview info for personal battery charging.
    Returns dict with: units, percent_gain, cost_per_unit, will_overcharge, final_percent, capped_amount
    """
    units = convert_to_personal_units(resource_key, amount, total_scrap, total_materials)
    percent_gain = units  # 1 unit = 1%
    final_percent = min(PERSONAL_MAX_CHARGE, current_percent + percent_gain)
    will_overcharge = final_percent > 100
    
    # Calculate cost per 1 unit (1%)
    if resource_key == "scrap":
        cost_per_unit = int(math.ceil(total_scrap * PERSONAL_SCRAP_PERCENT_PER_UNIT / 100))
    else:
        cost_per_unit = int(math.ceil(total_materials * PERSONAL_MATERIALS_PERCENT_PER_UNIT / 100))
    
    # Check if capped by max charge
    max_units_allowed = (PERSONAL_MAX_CHARGE - current_percent)
    capped_units = min(units, max_units_allowed)
    capped_amount = amount if capped_units == units else int(capped_units * cost_per_unit)
    
    return {
        "units": capped_units,
        "percent_gain": capped_units,
        "cost_per_unit": cost_per_unit,
        "will_overcharge": will_overcharge,
        "final_percent": min(PERSONAL_MAX_CHARGE, current_percent + capped_units),
        "capped_amount": capped_amount,
        "was_capped": capped_units < units
    }

def get_charge_preview_mega(resource_key: str, amount: int, total_scrap: int, total_materials: int, current_percent: int, units_contributed_last_hour: int) -> Dict[str, Any]:
    """
    Calculate preview info for mega weapon charging.
    Returns dict with: units, percent_gain, cost_per_unit, will_fire, rate_limited, capped_amount, available_capacity
    """
    units = convert_to_mega_units(resource_key, amount, total_scrap, total_materials)
    percent_gain = units  # 1 unit = 1%
    will_fire = (current_percent + percent_gain) >= 100
    
    # Calculate cost per 1 unit (1%)
    if resource_key == "scrap":
        cost_per_unit = int(math.ceil(total_scrap * MEGA_SCRAP_PERCENT_PER_UNIT / 100))
    else:
        cost_per_unit = int(math.ceil(total_materials * MEGA_MATERIALS_PERCENT_PER_UNIT / 100))
    
    # Check rate limit (10% per hour)
    max_units_per_hour = MEGA_TARGET_UNITS * MEGA_HOURLY_CONTRIBUTION_LIMIT // 100  # 10 units
    available_capacity = max(0, max_units_per_hour - units_contributed_last_hour)
    
    rate_limited = units > available_capacity
    capped_units = min(units, available_capacity)
    capped_amount = amount if capped_units == units else int(capped_units * cost_per_unit)
    
    return {
        "units": capped_units,
        "percent_gain": capped_units,
        "cost_per_unit": cost_per_unit,
        "will_fire": (current_percent + capped_units) >= 100,
        "rate_limited": rate_limited,
        "capped_amount": capped_amount,
        "available_capacity": available_capacity
    }

def _payout(active: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]]]:
    """
    Compute payouts (Scrap and Supply Crates) by uid using rank bands.
    Returns (scrap_payouts, supply_crate_payouts) where:
    - scrap_payouts: {uid: scrap_amount}
    - supply_crate_payouts: {uid: {item_id: quantity}}
    """
    contribs = active.get("contributors", {})
    if not contribs:
        return ({}, {})
    
    # Sort by damage descending
    ranked = sorted(contribs.items(), key=lambda kv: -int(kv[1].get("damage", 0)))
    pool = int(active.get("reward_pool", BASE_REWARD_POOL_SCRAP))
    scrap_payouts: Dict[str, int] = {}
    crate_payouts: Dict[str, Dict[str, int]] = {}
    
    for rank, (uid, ent) in enumerate(ranked, 1):
        # Find the band for this rank
        reward_frac = 0.0
        band_num = 5  # default to band 5 (11+)
        for max_rank, frac in RANK_BANDS:
            if rank <= max_rank:
                reward_frac = frac
                # Determine band number for supply crate rewards
                if max_rank == 1:
                    band_num = 1
                elif max_rank == 3:
                    band_num = 2
                elif max_rank == 5:
                    band_num = 3
                elif max_rank == 10:
                    band_num = 4
                else:
                    band_num = 5
                break
        
        # Scrap payout
        amt = int(math.floor(pool * reward_frac))
        if amt > 0:
            scrap_payouts[str(uid)] = amt
        
        # Supply crate payout
        crate_rewards = SUPPLY_CRATE_REWARDS.get(band_num, {})
        if crate_rewards:
            crate_payouts[str(uid)] = dict(crate_rewards)
    
    return (scrap_payouts, crate_payouts)

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
        scrap_payouts, crate_payouts = _payout(act)
    else:
        # consolation pool: 10%
        pool = int(max(0, int(act.get("reward_pool", BASE_REWARD_POOL_SCRAP)) * CONSOLATION_POOL_FRACTION))
        act2 = dict(act)
        act2["reward_pool"] = pool
        scrap_payouts, crate_payouts = _payout(act2)

    summary = {
        "raid_id": act.get("raid_id"),
        "boss_name": act.get("boss_name"),
        "hp_max": int(act.get("hp_max", 0)),
        "duration": int(max(0, _now() - int(act.get("started_at", _now())))),
        "reason": reason,
        "success": success,
        "payouts": scrap_payouts,  # uid -> scrap
        "crate_payouts": crate_payouts,  # uid -> {item_id: quantity}
        "top": sorted(((uid, int(e.get("damage", 0))) for uid, e in act.get("contributors", {}).items()), key=lambda kv: -kv[1])[:10],
        "ended_at": _now(),
        "claimed": [],  # track who has claimed payouts
    }
    # archive and clear active
    hist = state.setdefault("history", [])
    hist.append(summary)
    state["active"] = None
    return summary

def claim_payout(state: Dict[str, Any], uid: str) -> Tuple[int, Dict[str, int], Dict[str, Any]]:
    """
    Allow a player to claim their payout from the most recent summary. 
    Returns (scrap_amount, supply_crates_dict, summary) where supply_crates_dict is {item_id: quantity}.
    """
    hist = state.get("history", [])
    if not hist:
        return (0, {}, {})
    latest = hist[-1]
    if state.get("active") is not None:  # cannot claim while active raid
        return (0, {}, latest)
    claimed = latest.setdefault("claimed", [])
    if str(uid) in claimed:
        return (0, {}, latest)
    scrap_amount = int(latest.get("payouts", {}).get(str(uid), 0))
    crate_rewards = latest.get("crate_payouts", {}).get(str(uid), {})
    if scrap_amount > 0 or crate_rewards:
        claimed.append(str(uid))
    return (scrap_amount, crate_rewards, latest)

