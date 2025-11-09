# systems/combat.py
import random
from typing import List
from core.shared import load_json
from core.constants import ENEMIES_FILE
from core.utils import get_max_health
from core.players import calculate_combat_stats
from systems.ship_sys import derive_ship_effects
from core.skills_hooks import supply_crate_effects
from core.sector import ensure_sector, sector_bonus_multiplier


# ===== Supply Crate drop config =====
BASE_SUPPLY_CRATE_CHANCE = {
    "scan": 0.015,     # 1.5% base on basic fights
    "explore": 0.040,  # 4.0% base on elite fights
}

RARITY_WEIGHTS = {
    "scan": {
        "common": 75.0,
        "uncommon": 14.99,
        "rare": 8.999889,
        "mythic": 1.0,
        "legendary": 0.01,
        "solar": 0.0001,
        "galactic": 1e-5,
        "universal": 1e-6,
    },
    "explore": {
        "common": 57.0,
        "uncommon": 22.0,
        "rare": 14.998989,
        "mythic": 5.0,
        "legendary": 1.0,
        "solar": 0.001,
        "galactic": 1e-5,
        "universal": 1e-6,
    },
}

RARITY_TO_ID = {
    "common": "300",
    "uncommon": "301",
    "rare": "302",
    "mythic": "303",
    "legendary": "304",
    "solar": "305",
    "galactic": "306",
    "universal": "307",
}

def _roll_supply_crate_rarity(fight_type: str) -> str:
    ft = "explore" if fight_type == "explore" else "scan"
    table = RARITY_WEIGHTS[ft]
    names = list(table.keys())
    weights = list(table.values())
    return random.choices(names, weights=weights, k=1)[0]

def roll_supply_crate_drop(player: dict, fight_type: str) -> List[str]:
    """
    Returns a list of supply crate item_ids dropped this fight.
    Skill effects: supply_crate_mult (chance) and extra_supply_crates (extra rolls).
    Ship effects: double_supply_crates (adds one extra independent roll) but only when a base crate drops.
    Boxer extras apply ONLY if at least one base crate drops.
    Sector multiplies the drop chance.
    """
    sk = supply_crate_effects(player)
    mult = float(sk.get("supply_crate_mult", 1.0))
    extra_from_skill = int(sk.get("extra_supply_crates", 0))

    ship_eff = derive_ship_effects(player) or {}
    ship_double = bool(ship_eff.get("double_supply_crates"))

    base = float(BASE_SUPPLY_CRATE_CHANCE.get("explore" if fight_type == "explore" else "scan", 0.0))

    # Sector: boosts probabilities (capped to avoid certainty)
    sec = ensure_sector(player)
    sec_mult = sector_bonus_multiplier(sec)

    # Final chance after sector + skill mult
    chance = max(0.0, min(0.95, base * max(0.0, mult) * max(0.0, sec_mult)))

    drops: List[str] = []
    base_hit = False

    # Primary roll
    if random.random() < chance:
        rar = _roll_supply_crate_rarity(fight_type)
        drops.append(RARITY_TO_ID.get(rar, "300"))
        base_hit = True

        # Ship “double_supply_crates” (independent extra roll) - only if base crate dropped
        if ship_double:
            rar2 = _roll_supply_crate_rarity(fight_type)
            drops.append(RARITY_TO_ID.get(rar2, "300"))

        # Extra crates from Boxer (only if base crate hit)
        for _ in range(max(0, extra_from_skill)):
            rarx = _roll_supply_crate_rarity(fight_type)
            drops.append(RARITY_TO_ID.get(rarx, "300"))

    return drops

def _unique_non_loot_drops_list(drops):
    """
    Keep at most one of each non-supply-crate token; ignore 'Supply Crate' tokens here (handled by roll_supply_crate_drop).
    """
    out = []
    seen = set()
    for d in (drops or []):
        sid = str(d)
        if sid.lower() == "supply_crate":
            continue
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out

def _roll_enemy_drops(player: dict, enemy: dict, rng=random) -> list[str]:
    """
    Roll enemy-native drops (non-supply-crate). Each unique non-supply-crate item is rolled once.
    Sector multiplies the per-entry chance. No ship double-drops here (apply later in scan/explore if needed).
    """
    tokens = _unique_non_loot_drops_list(enemy.get("drops", []))
    base_chance = float(enemy.get("drop_chance", 0.02))  # fallback 2% per entry
    sec = ensure_sector(player)
    sec_mult = sector_bonus_multiplier(sec)
    chance = max(0.0, min(0.95, base_chance * max(0.0, sec_mult)))
    out: list[str] = []
    for tok in tokens:
        if rng.random() < chance:
            out.append(tok)
    return out


def calculate_damage(attacker, defender):
    attack = attacker.get("attack", 0)
    defense = defender.get("defense", 0)
    base_damage = max(1, attack - defense * 0.5)
    if random.random() < 0.1:
        base_damage *= 1.5
    return int(base_damage)

def simulate_combat(player, enemy, fight_type: str):
    """
    Simulate a full fight until one side dies.
    fight_type: 'scan' (basic) or 'explore' (elite)
    Returns:
      player_won, enemy_hp_left, player_hp_left, rounds, drops[list[item_id or tokens]]
    """
    stats = calculate_combat_stats(player)
    player_hp = player.get("health", get_max_health(player))
    enemy_hp = enemy["hp"]
    rounds = 0
    drops: List[str] = []

    while player_hp > 0 and enemy_hp > 0:
        rounds += 1
        player_damage = max(stats["attack"] - enemy.get("defense", 0), 1)
        enemy_damage = max(enemy.get("attack", 0) - stats["defense"], 0)
        enemy_hp -= player_damage
        player_hp -= enemy_damage

    player_won = enemy_hp <= 0 and player_hp > 0

    if player_won:
        # non-supply-crate drops (deduped)
        drops.extend(_roll_enemy_drops(player, enemy))
        # Supply Cratees (chance × Boxer, extras gated by base hit, ship double on base hit)
        drops.extend(roll_supply_crate_drop(player, fight_type))

    return {
        "player_won": player_won,
        "enemy_hp_left": max(enemy_hp, 0),
        "player_hp_left": max(player_hp, 0),
        "rounds": rounds,
        "drops": drops
    }


def choose_random_enemy(player, category="basic"):
    planet_id = str(player.get("current_planet", 1))
    enemies_data = load_json(ENEMIES_FILE).get(f"P{planet_id}E", {})

    valid_enemies = {k: v for k, v in enemies_data.items() if v.get("category") == category}
    if not valid_enemies:
        return None, None

    enemy_key = random.choice(list(valid_enemies.keys()))
    return enemy_key, valid_enemies[enemy_key]
