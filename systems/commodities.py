import os, json, time, math
from typing import Dict, Iterable, Tuple
from discord.ext import tasks
from core.shared import load_json
from core.constants import ITEMS_FILE

PROFILE_DIR = os.path.join("data", "players")
STATE_FILE = os.path.join("data", "commodities.json")
TICK_SECONDS = 300
HISTORY_MAX = 288

# Price model knobs
BASE_PRICE = 100.0          # anchor price when supply is at baseline
TOT_EMA_ALPHA = 0.30        # smoothing for supply (owned totals)
PRICE_EMA_ALPHA = 0.40      # smoothing for price toward intrinsic
SCARCITY_EXP = 0.60         # price sensitivity to scarcity (higher -> more sensitive)
MOVE_CAP = 0.15             # max ±15% per tick movement
MIN_PRICE = 1.0
MAX_PRICE = 1_000_000.0

CHAINS = {
    "plasteel": ["plasteel", "plasteel sheet", "plasteel bar", "plasteel beam", "plasteel block"],
    "circuit":  ["circuit", "microchip", "processor", "motherboard", "quantum computer"],
    "plasma":   ["plasma", "plasma slag", "plasma charge", "plasma core", "plasma module"],
    "biofiber": ["biofiber", "biopolymer", "bio gel", "bio metal hybrid", "bio material block"],
}
def tier_multiplier(tier_idx: int) -> int:
    return 10 ** int(tier_idx)

def _load_state() -> Dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def _save_state(state: Dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)

def _iter_profiles():
    # players.json (monolithic) support
    fallback = os.path.join("data", "players.json")
    if os.path.isfile(fallback):
        try:
            with open(fallback, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, dict):
                        yield v
            return
        except Exception:
            return
    # per-file dir support (unused today)
    if not os.path.isdir(PROFILE_DIR):
        return
    for name in os.listdir(PROFILE_DIR):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(PROFILE_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                prof = json.load(f) or {}
            if isinstance(prof, dict):
                yield prof
        except Exception:
            continue

def _build_chain_index(items_data: Dict) -> Dict[str, Dict[str, int]]:
    idx: Dict[str, Dict[str, int]] = {b: {} for b in CHAINS.keys()}
    entries = []
    if isinstance(items_data, dict):
        for cat, items in items_data.items():
            if not isinstance(items, dict): continue
            for iid, meta in items.items():
                nm = str((meta or {}).get("name", "")).strip().lower()
                if nm: entries.append((str(iid), nm))
    for base, names in CHAINS.items():
        for t_idx, nm in enumerate(names):
            mult = tier_multiplier(t_idx)
            target = nm.strip().lower()
            for iid, nm_lc in entries:
                if nm_lc == target:
                    idx[base][iid] = mult
    return idx

def _sum_owned_equiv(chain_index: Dict[str, Dict[str, int]]) -> Dict[str, int]:
    totals = {b: 0 for b in CHAINS.keys()}
    for prof in _iter_profiles():
        inv = prof.get("inventory", {}) or {}
        if not isinstance(inv, dict): continue
        for base, mapping in chain_index.items():
            for iid, mult in mapping.items():
                qty = int(inv.get(iid, 0) or 0)
                if qty > 0:
                    totals[base] += qty * int(mult)
    return totals

def _cap_move(prev: float, target: float) -> float:
    if prev <= 0: return target
    cap = MOVE_CAP * prev
    delta = max(-cap, min(cap, target - prev))
    return prev + delta

@tasks.loop(seconds=TICK_SECONDS)
async def commodities_tick():
    items_data = load_json(ITEMS_FILE) or {}
    chain_index = _build_chain_index(items_data)
    now = int(time.time())

    state = _load_state()
    bases = state.get("bases") or {}
    new_totals = _sum_owned_equiv(chain_index)

    for base in CHAINS.keys():
        b = bases.get(base) or {"total": 0, "history": [], "ema_total": None, "price": BASE_PRICE, "ema_price": None}
        prev_total = int(b.get("total", 0) or 0)
        cur_total = int(new_totals.get(base, 0) or 0)

        # Update total and total EMA (supply smoothing)
        ema_t = b.get("ema_total")
        if ema_t is None: ema_t = float(cur_total or prev_total or 1)
        else: ema_t = (1 - TOT_EMA_ALPHA) * float(ema_t) + TOT_EMA_ALPHA * float(cur_total or 0)

        # Intrinsic price rises when supply (total) drops vs its EMA, and falls when supply rises.
        ratio = float(ema_t) / max(1.0, float(cur_total))
        intrinsic = BASE_PRICE * (ratio ** SCARCITY_EXP)
        intrinsic = max(MIN_PRICE, min(MAX_PRICE, intrinsic))

        # Smooth price and cap per-tick movement
        prev_price = float(b.get("price") or BASE_PRICE)
        ema_price = b.get("ema_price")
        if ema_price is None: ema_price = intrinsic
        else: ema_price = (1 - PRICE_EMA_ALPHA) * float(ema_price) + PRICE_EMA_ALPHA * float(intrinsic)
        capped = _cap_move(prev_price, ema_price)

        # History and deltas
        delta = cur_total - prev_total
        pct = (delta / prev_total * 100.0) if prev_total > 0 else 0.0

        b["total"] = cur_total
        b["ema_total"] = float(round(ema_t, 4))
        b["price"] = float(round(capped, 2))
        b["ema_price"] = float(round(ema_price, 4))
        hist = b.get("history") or []
        hist.append({"t": now, "total": cur_total, "price": b["price"]})
        if len(hist) > HISTORY_MAX: hist = hist[-HISTORY_MAX:]
        b["history"] = hist
        b["last_delta"] = delta
        b["last_pct"] = round(pct, 2)
        bases[base] = b

    state["bases"] = bases
    state["last_update"] = now
    _save_state(state)

def ensure_started():
    if not commodities_tick.is_running():
        commodities_tick.start()

def _load_public_state() -> Dict:
    return _load_state()

def get_quote(base: str) -> float:
    """
    Returns current price per base unit for the commodity.
    """
    st = _load_state()
    b = (st.get("bases") or {}).get(str(base).lower() , None)
    if not b:
        return float(BASE_PRICE)
    return float(b.get("price", BASE_PRICE))