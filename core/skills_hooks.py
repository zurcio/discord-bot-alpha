from __future__ import annotations
import logging
from typing import Optional, Tuple
from core.constants import SKILLS_ENABLED, SKILLS_VERBOSE, SKILLS_LOG_CHANNEL_ID
from core.skills import award_skill_xp, compute_perks, get_level, is_overcharged, can_overcharge, set_overcharged

log = logging.getLogger(__name__)

def award_skill(ctx, skill: str, amount: int) -> Tuple[int, int]:
    """
    Award skill XP safely. Returns (new_level, levels_gained).
    Use for: worker, crafter, tinkerer, trader, boxer, gambler, soldier.
    """
    if not SKILLS_ENABLED or amount <= 0:
        return (0, 0)
    player = ctx.player
    lvl, up = award_skill_xp(player, skill, int(amount))
    if SKILLS_VERBOSE:
        who = f"{ctx.author}({ctx.author.id})"
        log.info(f"[skills] {who} +{amount} {skill} xp -> L{lvl} (+{up})")
    return (lvl, up)

def perks_for(player: dict) -> dict:
    return compute_perks(player or {})

# NEW: Flattened, skill-derived effects for systems to consume without touching ship_sys
def effects_for(player: dict) -> dict:
    """
    Returns a flat dict of skill-driven effects. Safe to import in combat/sell/tinker/work/etc.
    Keys:
      - lootbox_mult, extra_lootboxes
      - sell_price_mult
      - tinker_high_tier_weight_mult, tinker_scrap_refund_chance
      - ship_upgrade_cost_reduction, ship_max_level_bonus
      - work_tier_weight_mult, cross_material_chance
      - craft_refund_pct
      - overcharged
    """
    pk = perks_for(player)
    boxer = pk.get("boxer", {}) or {}
    trader = pk.get("trader", {}) or {}
    tink = pk.get("tinkerer", {}) or {}
    soldi = pk.get("soldier", {}) or {}
    work = pk.get("worker", {}) or {}
    craft = pk.get("crafter", {}) or {}
    return {
        "lootbox_mult": float(boxer.get("lootbox_chance_mult", 1.0)),
        "extra_lootboxes": int(boxer.get("extra_lootboxes", 0)),
        "sell_price_mult": float(trader.get("sell_price_mult", 1.0)),
        "tinker_high_tier_weight_mult": float(tink.get("tinker_high_tier_weight_mult", 1.0)),
        "tinker_scrap_refund_chance": float(tink.get("tinker_scrap_refund_chance", 0.0)),
        "ship_upgrade_cost_reduction": float(soldi.get("ship_upgrade_cost_reduction", 0.0)),
        "ship_max_level_bonus": int(soldi.get("ship_max_level_bonus", 0)),
        "work_tier_weight_mult": float(work.get("work_tier_weight_mult", 1.0)),
        "cross_material_chance": float(work.get("cross_material_chance", 0.0)),
        "craft_refund_pct": float(craft.get("craft_refund_pct", 0.0)),
        "overcharged": bool(pk.get("overcharged", False)),
    }

# NEW: Focused helpers (import these in modules as needed)

def lootbox_effects(player: dict) -> dict:
    ef = effects_for(player)
    return {
        "lootbox_mult": ef["lootbox_mult"],
        "extra_lootboxes": ef["extra_lootboxes"],
    }

def trader_effects(player: dict) -> dict:
    ef = effects_for(player)
    return {"sell_price_mult": ef["sell_price_mult"]}

def tinkerer_effects(player: dict) -> dict:
    ef = effects_for(player)
    return {
        "tinker_high_tier_weight_mult": ef["tinker_high_tier_weight_mult"],
        "tinker_scrap_refund_chance": ef["tinker_scrap_refund_chance"],
    }

def soldier_effects(player: dict) -> dict:
    ef = effects_for(player)
    return {
        "ship_upgrade_cost_reduction": ef["ship_upgrade_cost_reduction"],
        "ship_max_level_bonus": ef["ship_max_level_bonus"],
    }

def worker_effects(player: dict) -> dict:
    ef = effects_for(player)
    return {
        "work_tier_weight_mult": ef["work_tier_weight_mult"],
        "cross_material_chance": ef["cross_material_chance"],
        "overcharged": ef["overcharged"],
    }

def crafter_effects(player: dict) -> dict:
    ef = effects_for(player)
    return {"craft_refund_pct": ef["craft_refund_pct"]}


def gambler_effects(player: dict) -> dict:
    pk = perks_for(player)
    g = pk.get("gambler", {}) or {}
    return {
        "bank_xp_mult": float(g.get("bank_xp_mult", 1.0)),
        "daily_interest_rate": float(g.get("daily_interest_rate", 0.0)),
    }

def award_player_skill(player: dict, skill: str, amount: int) -> Tuple[int, int]:
    """
    Award skill XP for a given player profile. Returns (new_level, levels_gained).
    Use when you don't have a ctx (e.g., systems layer).
    """
    if not SKILLS_ENABLED or amount <= 0:
        return (0, 0)
    return award_skill_xp(player, str(skill).lower(), int(amount))


async def maybe_log_to_channel(bot, message: str):
    if not SKILLS_VERBOSE or not SKILLS_LOG_CHANNEL_ID:
        return
    ch = bot.get_channel(SKILLS_LOG_CHANNEL_ID)
    if ch:
        try:
            await ch.send(message[:1900])
        except Exception:
            pass

def skill_level(player: dict, name: str) -> int:
    return get_level(player, name)

def is_player_overcharged(player: dict) -> bool:
    return is_overcharged(player)

def try_enable_overcharged(player: dict) -> bool:
    if can_overcharge(player):
        set_overcharged(player, True)
        return True
    return False


def _norm_key(s: str) -> str:
    s = str(s or "")
    out = []
    last_us = False
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            last_us = False
        else:
            if not last_us:
                out.append("_")
                last_us = True
    return "".join(out).strip("_")

# Exact per-item Trader XP (per unit sold)
_SELL_XP = {
    # Base families
    "plasteel": 1,
    "circuit": 1,
    "plasma": 5,
    "biofiber": 10,

    # Plasteel line
    "plasteel_sheet": 2,
    "plasteel_bar": 25,
    "plasteel_beam": 50,
    "plasteel_block": 100,

    # Circuit line
    "microchip": 2,
    "processor": 25,
    "motherboard": 50,
    "quantum_computer": 100,

    # Plasma line
    "plasma_slag": 10,
    "plasma_charge": 50,
    "plasma_core": 100,
    "plasma_module": 200,

    # Biofiber line
    "biopolymer": 20,
    "bio_gel": 50,
    "bio_metal_hybrid": 100,
    "bio-material_hybrid": 100,   # alias (hyphen variant)
    "bio_material_block": 200,
    "bio-material_block": 200,    # alias (hyphen variant)

    # Enemy drops line
    "crawler_tail": 3,
    "slug_slime": 5,
    "orchid_bloom": 7,
    "crystal_shard": 10,
    "lithium_ion": 15,
}

def trader_xp_for_item(item_id: str | int, item_name: str | None = None) -> int:
    """
    Returns Trader XP for selling ONE unit of the given item.
    Matches by normalized id or normalized display name.
    """
    # Direct id match (if someone uses ids as keys)
    sid = str(item_id)
    if sid in _SELL_XP:
        return int(_SELL_XP[sid])

    # Normalized id match
    nk = _norm_key(sid)
    if nk in _SELL_XP:
        return int(_SELL_XP[nk])

    # Normalized name match
    if item_name:
        nn = _norm_key(item_name)
        if nn in _SELL_XP:
            return int(_SELL_XP[nn])

    return 0