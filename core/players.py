from core.shared import load_json, save_json
from core.constants import ITEMS_FILE, PLAYERS_FILE
from core.items import get_item_by_id
from systems.ship_sys import derive_ship_effects
import time


def load_players():
    return load_json(PLAYERS_FILE)

def save_players(data):
    save_json(PLAYERS_FILE, data)

def _normalize_currency(profile: dict) -> None:
    if not isinstance(profile, dict):
        return
    upper = int(profile.get("Scrap", 0) or 0)
    lower = int(profile.get("scrap", 0) or 0)
    profile["Scrap"] = upper + lower
    profile.pop("scrap", None)

def _normalize_inventory_map(inv: dict) -> dict:
    """Stringify keys, keep only positive int quantities, drop zeros/negatives."""
    out = {}
    if isinstance(inv, dict):
        for k, v in inv.items():
            sk = str(k)
            try:
                q = int(v)
            except Exception:
                q = 0
            if q > 0:
                out[sk] = q
    return out

def _normalize_inventory(profile: dict) -> None:
    if not isinstance(profile, dict):
        return
    inv = profile.get("inventory", {})
    profile["inventory"] = _normalize_inventory_map(inv)

def load_profile(user_id):
    players = load_players()
    prof = players.get(str(user_id))
    if isinstance(prof, dict):
        _normalize_currency(prof)
        _normalize_inventory(prof)
    return prof

def _deep_merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst

def save_profile(user_id, profile):
    """
    Save a profile safely:
    - Normalize currency and inventory in both current and incoming profile
    - Replace 'inventory' entirely from the incoming profile (so deletions persist)
    - Deep-merge other fields to preserve concurrent updates
    """
    players = load_players()
    uid = str(user_id)
    cur = players.get(uid, {})

    if isinstance(cur, dict):
        _normalize_currency(cur)
        _normalize_inventory(cur)

    incoming = profile if isinstance(profile, dict) else {}
    if isinstance(incoming, dict):
        _normalize_currency(incoming)
        _normalize_inventory(incoming)

    # Replace inventory (critical: allow consumption/removal)
    incoming_inv = incoming.get("inventory") if isinstance(incoming.get("inventory"), dict) else None

    # Merge everything except 'inventory'
    cur_merged = cur if isinstance(cur, dict) else {}
    src_no_inv = {k: v for k, v in (incoming.items() if isinstance(incoming, dict) else []) if k != "inventory"}
    merged = _deep_merge(cur_merged, src_no_inv)

    # Apply inventory replacement if provided, else keep normalized current
    if isinstance(incoming_inv, dict):
        merged["inventory"] = incoming_inv
    else:
        # ensure normalized
        merged["inventory"] = _normalize_inventory_map(merged.get("inventory", {}))

    players[uid] = merged
    save_players(players)

def get_scrap(profile: dict) -> int:
    return int(profile.get("Scrap", 0) or 0)

def set_scrap(profile: dict, value: int) -> None:
    profile["Scrap"] = int(value)



# def load_profile(user_id):
#     players = load_players()
#     return players.get(str(user_id))

# def save_profile(user_id, profile):
#     # players = load_players()
#     # players[str(user_id)] = profile
#     # save_players(players)


def default_profile(uid, username):
    return {
        "id": uid,
        "username": username,
        "Scrap": 0,
        "Credits": 0,
        "xp": 0,
        "level": 1,
        "health": 100,
        "oxygen": 100,
        "current_planet": 1,
        "max_unlocked_planet": 1,
        "inventory": {},
        "cooldowns": {},
        "active_quest": None,
        "completed_quests": [],
        "equipped": {"weapon": None, "armor": None},
        "enhancements": {},
        "bank": { "unlocked": False, "balance": 0 },
    }

def calculate_combat_stats(player):
    """Return combat stats = base per level + equipped bonuses with multipliers and enhancements."""
    level = player.get("level", 1)

    # Base scaling: +5 per level
    base_attack = 5 * level
    base_defense = 5 * level

    items = load_json(ITEMS_FILE)
    equipped = player.get("equipped", {}) or {}
    enhancements = player.get("enhancements", {}) or {}

    # Start from base stats
    attack = base_attack
    defense = base_defense

    # Default multipliers
    attack_mult = 1.0
    defense_mult = 1.0

    # Weapon
    weapon_id = equipped.get("weapon")
    if weapon_id:
        weapon = get_item_by_id(items, weapon_id)
        if weapon:
            w_base_atk = int(weapon.get("attack", 0) or 0)
            w_base_def = int(weapon.get("defense", 0) or 0)
            w_buff = float((enhancements.get(str(weapon_id)) or {}).get("buff", 0.0))
            # Enhancement applies multiplicatively to the gear stat only
            attack += int(round(w_base_atk * (1.0 + w_buff)))
            defense += int(round(w_base_def * (1.0 + w_buff)))
            attack_mult *= float(weapon.get("attack_mult", 1.0))
            defense_mult *= float(weapon.get("defense_mult", 1.0))

    # Armor
    armor_id = equipped.get("armor")
    if armor_id:
        armor = get_item_by_id(items, armor_id)
        if armor:
            a_base_atk = int(armor.get("attack", 0) or 0)
            a_base_def = int(armor.get("defense", 0) or 0)
            a_buff = float((enhancements.get(str(armor_id)) or {}).get("buff", 0.0))
            attack += int(round(a_base_atk * (1.0 + a_buff)))
            defense += int(round(a_base_def * (1.0 + a_buff)))
            attack_mult *= float(armor.get("attack_mult", 1.0))
            defense_mult *= float(armor.get("defense_mult", 1.0))

    # Apply multipliers to total
    final_attack = int(attack * attack_mult)
    final_defense = int(defense * defense_mult)

    # Ship type boosts for attack/defense
    eff = derive_ship_effects(player)
    tb = eff.get("type_boost", {})
    if tb and tb.get("stat") == "attack":
        final_attack = int(round(final_attack * (1.0 + float(tb.get("value", 0.0)))))
    if tb and tb.get("stat") == "defense":
        final_defense = int(round(final_defense * (1.0 + float(tb.get("value", 0.0)))))

    return {"attack": final_attack, "defense": final_defense}


def migrate_player(player, uid, username):
    """Migrate a single player profile in memory."""
    changed = False

    try:
        player["Credits"] = int(player.get("Credits", 0) or 0)
        changed = True  # if your function tracks 'changed', keep/update it accordingly
    except Exception:
        player["Credits"] = 0
        changed = True

    # Ensure equipped dict exists
    if "equipped" not in player or not isinstance(player["equipped"], dict):
        player["equipped"] = {"weapon": None, "armor": None}
        changed = True

    # Ensure enhancements dict exists
    if "enhancements" not in player or not isinstance(player["enhancements"], dict):
        player["enhancements"] = {}
        changed = True

    # Remove obsolete keys
    for key in ["attack", "defense", "equipped_weapon", "equipped_armor"]:
        if key in player:
            player.pop(key)
            changed = True

    # Add username if missing
    if "username" not in player:
        player["username"] = username
        changed = True

    # Ensure last_regen exists
    if "last_regen" not in player:
        player["last_regen"] = int(time.time())
        changed = True

    # Ensure active_tank exists and is valid
    if "active_tank" not in player or not isinstance(player["active_tank"], dict):
        player["active_tank"] = None
        changed = True
    else:
        if "id" not in player["active_tank"] or "remaining" not in player["active_tank"]:
            player["active_tank"] = None
            changed = True

    if "ship" not in player or not isinstance(player["ship"], dict):
        player["ship"] = {"owned": False, "tier": 0, "level": 0, "type": None, "attempts": {}}
        changed = True
    else:
        s = player["ship"]
        if "owned" not in s: s["owned"] = False; changed = True
        if "tier" not in s: s["tier"] = 0; changed = True
        if "level" not in s: s["level"] = 0; changed = True
        if "type" not in s: s["type"] = None; changed = True
        if "attempts" not in s or not isinstance(s["attempts"], dict): s["attempts"] = {}; changed = True

    # Ensure bank exists
    if "bank" not in player or not isinstance(player["bank"], dict):
        player["bank"] = {"unlocked": False, "balance": 0}
        changed = True
    else:
        b = player["bank"]
        if "unlocked" not in b or not isinstance(b.get("unlocked"), bool):
            b["unlocked"] = bool(b.get("unlocked", False)); changed = True
        if "balance" not in b or not isinstance(b.get("balance"), int):
            try:
                b["balance"] = int(b.get("balance", 0))
            except Exception:
                b["balance"] = 0
            changed = True
        player["bank"] = b
    return player