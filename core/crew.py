from __future__ import annotations
import random, string, time
from typing import Dict, List, Optional, Tuple
from core.shared import load_json
from core.constants import ITEMS_FILE

CREW_TYPES = ["soldier", "contractor", "scientist", "explorer"]
JOB_SECONDS = 4 * 60 * 60  # 4 hours

def capacity_for_sector(sector: int) -> int:
    return max(0, int(sector or 1) - 2)

def ensure_crew_struct(player: Dict) -> Dict:
    if "crew" not in player or not isinstance(player["crew"], list):
        player["crew"] = []
    return player

def _alpha_codes():
    # A..Z, AA..AZ, BA.. etc.
    letters = string.ascii_uppercase
    # length 1+
    length = 1
    while True:
        if length == 1:
            for ch in letters:
                yield ch
        else:
            # e.g., length=2 -> AA..ZZ
            def rec(prefix, depth):
                if depth == 0:
                    yield prefix
                    return
                for ch in letters:
                    yield from rec(prefix + ch, depth - 1)
            for ch in letters:
                for s in rec(ch, length - 1):
                    yield s
        length += 1

def next_crew_code(existing: List[str]) -> str:
    taken = {c.upper() for c in existing if isinstance(c, str)}
    for code in _alpha_codes():
        if code not in taken:
            return code

def resolve_medkit_key() -> str:
    items = load_json(ITEMS_FILE) or {}
    # Try to find “medkit” by name across categories
    if isinstance(items, dict):
        for cat, data in items.items():
            if not isinstance(data, dict):
                continue
            for iid, meta in data.items():
                nm = str(meta.get("name", "")).strip().lower()
                if nm in {"medkit", "med kit", "med-kit"}:
                    return str(iid)
    return "medkit"

def parse_offer_string(s: str, max_tokens: int = 6) -> Tuple[int, int, int]:
    """
    Returns (scrap_offer_total, medkits_offer_total, tokens_used).
    scrap token=1000; med token=1.
    """
    if not s:
        return 0, 0, 0
    scrap = med = used = 0
    for tok in s.lower().strip().split():
        if used >= max_tokens:
            break
        if tok in {"scrap", "s"}:
            scrap += 1000
            used += 1
        elif tok in {"med", "m", "medkit", "medkits"}:
            med += 1
            used += 1
    return scrap, med, used

def clamp_offer_to_wallet(player: Dict, scrap_offer: int, med_offer: int) -> Tuple[int, int]:
    inv = (player.get("inventory") or {})
    scrap_have = int(player.get("scrap", 0) or 0)
    med_key = resolve_medkit_key()
    med_have = int(inv.get(med_key, 0) or 0)
    return min(scrap_offer, scrap_have), min(med_offer, med_have)

def pay_now(player: Dict, scrap: int, meds: int) -> None:
    if scrap > 0:
        player["scrap"] = int(player.get("scrap", 0) or 0) - scrap
    if meds > 0:
        inv = player.get("inventory", {}) or {}
        med_key = resolve_medkit_key()
        inv[med_key] = int(inv.get(med_key, 0) or 0) - meds
        if inv[med_key] <= 0:
            inv.pop(med_key, None)
        player["inventory"] = inv

def spawn_candidate() -> Dict:
    return {
        "name": random.choice(["Avery", "Morgan", "Rhett", "Kai", "Nova", "Skye", "Vega", "Juno"]),
        "type": random.choice(CREW_TYPES),
        "salary_demand": random.choice([0, 1000, 2000, 3000, 4000, 5000]),
        "benefits_demand": random.randint(0, 5),
    }

def hire_probability(offer_scrap: int, offer_med: int, demand_scrap: int, demand_med: int) -> float:
    # Full meet → guaranteed
    if offer_scrap >= demand_scrap and offer_med >= demand_med:
        return 1.0
    # Handle zero-demand gracefully
    s_ratio = 1.0 if demand_scrap == 0 else (offer_scrap / demand_scrap)
    m_ratio = 1.0 if demand_med == 0 else (offer_med / demand_med)
    p = 0.5 * max(0.0, min(1.0, s_ratio)) + 0.5 * max(0.0, min(1.0, m_ratio))
    return max(0.05, min(0.95, p))

def add_hired_crew(player: Dict, candidate: Dict, per_job_scrap: int, per_job_meds: int, now: int | None = None) -> Dict:
    now = now or int(time.time())
    ensure_crew_struct(player)
    code = next_crew_code([c.get("code") for c in player["crew"]])
    crew = {
        "code": code,
        "name": candidate.get("name") or code,
        "type": candidate.get("type"),
        "cost_scrap": int(per_job_scrap),
        "cost_medkits": int(per_job_meds),
        "hired_at": now,
        "jobs_done": 0,
        "status": "idle",          # idle | working | ready
        "job_started": None,
        "job_ends": None,
        "pending_reward": None,    # payload when ready
    }
    player["crew"].append(crew)
    return crew

def start_job(player: Dict, crew: Dict, now: int, duration: int = JOB_SECONDS) -> Optional[str]:
    if crew.get("status") == "working":
        return "Crew already on a job."
    # Pay per-job cost now
    pay_now(player, int(crew.get("cost_scrap", 0)), int(crew.get("cost_medkits", 0)))
    crew["status"] = "working"
    crew["job_started"] = now
    crew["job_ends"] = now + int(duration)
    crew["pending_reward"] = None
    return None

def is_job_ready(crew: Dict, now: int) -> bool:
    ends = int(crew.get("job_ends") or 0)
    return crew.get("status") == "working" and ends > 0 and now >= ends

def finalize_job_reward(player: Dict, crew: Dict, sector: int, planet: int) -> Dict:
    """
    Build rewards based on crew type; tie to sector/planet; ignore other multipliers.
    TODO: respect double-drop effects for explorer where applicable.
    """
    ctype = crew.get("type")
    # Very rough placeholder scaling; adjust later
    s = max(1, int(sector or 1))
    p = max(1, int(planet or 1))
    reward = {"scrap": 0, "xp": 0, "items": {}}
    rng = random.Random()
    if ctype == "soldier":
        reward["scrap"] = 300 * s * p
    elif ctype == "contractor":
        # First-tier mats
        mat = random.choice(["plasteel", "circuit", "plasma", "biofiber"])
        qty = 10 + 3 * s + 2 * p
        reward["items"][mat] = qty
    elif ctype == "scientist":
        reward["xp"] = 250 * s * p
        if rng.random() < 0.15:
            reward.setdefault("lootboxes", {})["common"] = 1
    elif ctype == "explorer":
        reward["scrap"] = 150 * s * p
        # Placeholder: one enemy-drop-like item
        reward["items"]["plasteel"] = 5 + s + p
    return reward

def claim_job(player: Dict, crew: Dict, sector: int, planet: int, now: int) -> Tuple[bool, Optional[Dict]]:
    if crew.get("status") != "working":
        return False, None
    if not is_job_ready(crew, now):
        return False, None
    reward = finalize_job_reward(player, crew, sector, planet)
    # Apply to player
    if reward.get("scrap"):
        player["scrap"] = int(player.get("scrap", 0) or 0) + int(reward["scrap"])
    if reward.get("xp"):
        player["xp"] = int(player.get("xp", 0) or 0) + int(reward["xp"])
    inv = player.get("inventory", {}) or {}
    for k, v in (reward.get("items", {}) or {}).items():
        inv[str(k)] = int(inv.get(str(k), 0) or 0) + int(v)
    player["inventory"] = inv
    # Reset crew
    crew["status"] = "idle"
    crew["job_started"] = None
    crew["job_ends"] = None
    crew["pending_reward"] = None
    crew["jobs_done"] = int(crew.get("jobs_done", 0) or 0) + 1
    return True, reward