import math
from typing import Dict
from datetime import datetime, timezone
from core.utils import add_xp
from core.skills_hooks import gambler_effects
from core.constants import SKILLS_BANK_INTEREST_PRINCIPAL_CAP as INTEREST_CAP

MAX_XP_BOOST = 0.10
LOG_AT_CAP = 12.0
POWER = 3.5
COEFF = MAX_XP_BOOST / (LOG_AT_CAP ** POWER)

def _today_utc_ordinal() -> int:
    return datetime.now(timezone.utc).date().toordinal()

def ensure_bank(player: Dict) -> Dict:
    bank = player.get("bank")
    if not isinstance(bank, dict):
        bank = {"unlocked": False, "balance": 0}
        player["bank"] = bank
    else:
        bank.setdefault("unlocked", False)
        bank.setdefault("balance", 0)
    bank.setdefault("last_interest_day", _today_utc_ordinal())
    return bank

def compute_bank_boost_percent(balance: int) -> float:
    if balance <= 0:
        return 0.0
    x = math.log10(balance + 1.0)
    return min(MAX_XP_BOOST, COEFF * (x ** POWER))

def bank_xp_multiplier(player: Dict) -> float:
    bank = ensure_bank(player)
    if not bank.get("unlocked", False):
        return 1.0
    pct = compute_bank_boost_percent(int(bank.get("balance", 0)))
    g = gambler_effects(player)
    return (1.0 + pct) * float(g.get("bank_xp_mult", 1.0))

def add_xp_with_bank_bonus(player: Dict, base_xp: int) -> Dict:
    m = bank_xp_multiplier(player)
    boosted = int(round(base_xp * m))
    res = add_xp(player, boosted)
    res.update({
        "base_xp": int(base_xp),
        "boosted_xp": int(boosted),
        "multiplier": float(m),
        "boost_percent": float((m - 1.0))
    })
    return res

# Daily interest: compounded; interest applies only to first INTEREST_CAP Scrap of balance.
def maybe_apply_daily_interest(player: Dict) -> int:
    bank = ensure_bank(player)
    if not bank.get("unlocked", False):
        return 0
    rate = float(gambler_effects(player).get("daily_interest_rate", 0.0))
    today = _today_utc_ordinal()
    last = int(bank.get("last_interest_day", today))
    days = max(0, today - last)

    if days <= 0 or rate <= 0.0:
        bank["last_interest_day"] = today
        return 0

    bal = int(bank.get("balance", 0))
    if bal <= 0:
        bank["last_interest_day"] = today
        return 0

    principal = min(bal, int(INTEREST_CAP))
    # Compound interest on the capped principal only
    factor = (1.0 + rate) ** days
    interest = int(math.floor(principal * (factor - 1.0)))

    bank["balance"] = bal + max(0, interest)
    bank["last_interest_day"] = today
    player["bank"] = bank
    return max(0, interest)