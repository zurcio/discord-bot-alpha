import argparse
import random
import statistics
from typing import List, Dict, Tuple, Optional
from core.shared import load_json
from core.constants import BOSSES_FILE

# Generic ability set (mirrors your bossfight_sys weighting and params)
GENERIC_ABILITIES = [
    {"name": "Claw Strike",   "hit_chance": 0.85, "damage_mult": 1.0, "defense_pen": 0.0},
    {"name": "Savage Bite",   "hit_chance": 0.55, "damage_mult": 1.2, "defense_pen": 0.0},
    {"name": "Rage Stomp",    "hit_chance": 0.30, "damage_mult": 1.5, "defense_pen": 0.5},
]
GENERIC_WEIGHTS = [60, 30, 10]

def parse_player(s: str) -> Dict:
    """
    Parse player spec strings like:
      "atk=50,def=45,hp=150" or "name=Alice,atk=60,def=55,hp=170"
    """
    result = {"name": None, "atk": 50, "def": 50, "hp": 150}
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if k == "name":
            result["name"] = v
        elif k in ("atk", "attack"):
            result["atk"] = int(v)
        elif k in ("def", "defense"):
            result["def"] = int(v)
        elif k in ("hp", "health"):
            result["hp"] = int(v)
    return result

def default_players(n: int) -> List[Dict]:
    # Simple default: level ~10 feel (atk/def 50, hp 150)
    players = []
    for i in range(n):
        players.append({"name": f"P{i+1}", "atk": 50, "def": 50, "hp": 150})
    return players

def load_boss_from_file(boss_id: str) -> Optional[Dict]:
    bosses = load_json(BOSSES_FILE) or {}
    if boss_id in bosses:
        b = bosses[boss_id]
        return {
            "name": b.get("name", boss_id),
            "hp": int(b.get("hp", 1) or 1),
            "atk": int(b.get("attack", 1) or 1),
            "def": int(b.get("defense", 0) or 0),
            "abilities": list((b.get("abilities") or {}).values()) or GENERIC_ABILITIES,
        }
    return None

def simulate_once(players: List[Dict], boss: Dict, rng: random.Random) -> Tuple[bool, int, Dict]:
    """
    One fight simulation.
    - Players attack in order; each uses a basic 'attack' (0.8 hit chance; dmg=max(1, atk - boss_def))
    - After each player action (if boss alive), boss attacks that same player using weighted abilities
    - Fight ends when boss_hp<=0 or all players dead.
    Returns (player_won, rounds, snapshot)
    """
    # Copy mutable state
    combat_players = [
        {"name": p.get("name") or f"P{i+1}", "atk": int(p["atk"]), "def": int(p["def"]), "hp": int(p["hp"])}
        for i, p in enumerate(players)
    ]
    boss_hp = int(boss["hp"])
    boss_atk = int(boss["atk"])
    boss_def = int(boss["def"])
    abilities = boss.get("abilities") or GENERIC_ABILITIES

    rounds = 0
    alive_indices = [i for i, pl in enumerate(combat_players) if pl["hp"] > 0]

    while boss_hp > 0 and alive_indices:
        for idx in list(alive_indices):
            if boss_hp <= 0 or not alive_indices:
                break

            pl = combat_players[idx]
            if pl["hp"] <= 0:
                # refresh alive list and continue
                alive_indices = [i for i, x in enumerate(combat_players) if x["hp"] > 0]
                continue

            rounds += 1

            # Player attack (simple attack action)
            if rng.random() < 0.8:
                dmg_to_boss = max(1, pl["atk"] - boss_def)
                boss_hp -= dmg_to_boss
                if boss_hp <= 0:
                    break

            # Boss attacks this player
            # Weighted pick of ability
            if len(abilities) >= 3:
                ability = rng.choices(abilities, weights=GENERIC_WEIGHTS, k=1)[0]
            else:
                ability = rng.choice(abilities)

            if rng.random() < float(ability.get("hit_chance", 0.8)):
                dmg_mult = float(ability.get("damage_mult", 1.0))
                def_pen = float(ability.get("defense_pen", 0.0))
                effective_def = int(pl["def"] * (1.0 - def_pen))
                dmg_taken = max(1, int(boss_atk * dmg_mult) - effective_def)
                pl["hp"] -= dmg_taken

            # Refresh alive list
            alive_indices = [i for i, x in enumerate(combat_players) if x["hp"] > 0]
            if not alive_indices:
                break

    player_won = boss_hp <= 0 and any(pl["hp"] > 0 for pl in combat_players)
    snapshot = {
        "boss_hp_left": max(0, boss_hp),
        "players": [{"name": p["name"], "hp": max(0, p["hp"])} for p in combat_players],
    }
    return player_won, rounds, snapshot

def run_trials(players: List[Dict], boss: Dict, trials: int, seed: Optional[int]) -> Dict:
    rng = random.Random(seed)
    wins = 0
    rounds_list = []
    boss_hp_left = []
    survivors = []

    for _ in range(trials):
        won, r, snap = simulate_once(players, boss, rng)
        wins += 1 if won else 0
        rounds_list.append(r)
        boss_hp_left.append(snap["boss_hp_left"])
        survivors.append(sum(1 for p in snap["players"] if p["hp"] > 0))

    out = {
        "trials": trials,
        "win_rate": wins / trials,
        "avg_rounds": statistics.mean(rounds_list),
        "median_rounds": statistics.median(rounds_list),
        "avg_boss_hp_left": statistics.mean(boss_hp_left),
        "avg_survivors": statistics.mean(survivors),
        "min_rounds": min(rounds_list),
        "max_rounds": max(rounds_list),
    }
    return out

def main():
    ap = argparse.ArgumentParser(description="Bossfight stat tester (no Discord, fast iteration)")
    ap.add_argument("--boss-id", type=str, help="Load boss template from bosses.json (optional)")
    ap.add_argument("--boss-hp", type=int, help="Override boss HP")
    ap.add_argument("--boss-atk", type=int, help="Override boss Attack")
    ap.add_argument("--boss-def", type=int, help="Override boss Defense")
    ap.add_argument("--players", nargs="*", default=[], help='Player specs like "name=A,atk=60,def=55,hp=170" (repeatable)')
    ap.add_argument("--player-count", type=int, default=1, help="If --players omitted, use N default players")
    ap.add_argument("--trials", type=int, default=1000, help="Monte Carlo trials")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed (optional)")
    args = ap.parse_args()

    # Boss
    boss = {"name": "Test Boss", "hp": 500, "atk": 85, "def": 25, "abilities": GENERIC_ABILITIES}
    if args.boss_id:
        loaded = load_boss_from_file(args.boss_id)
        if loaded:
            boss.update(loaded)
            boss["name"] = loaded.get("name", boss["name"])
        else:
            print(f"Warning: boss_id '{args.boss_id}' not found. Using defaults.")
    if args.boss_hp is not None:  boss["hp"] = int(args.boss_hp)
    if args.boss_atk is not None: boss["atk"] = int(args.boss_atk)
    if args.boss_def is not None: boss["def"] = int(args.boss_def)

    # Players
    if args.players:
        players = [parse_player(s) for s in args.players]
        # Fill names if missing
        for i, p in enumerate(players):
            if not p["name"]:
                p["name"] = f"P{i+1}"
    else:
        players = default_players(max(1, args.player_count))

    print(f"Boss: {boss['name']} | HP {boss['hp']} | ATK {boss['atk']} | DEF {boss['def']}")
    for i, p in enumerate(players, 1):
        print(f"Player {i}: {p['name']} | ATK {p['atk']} | DEF {p['def']} | HP {p['hp']}")

    res = run_trials(players, boss, trials=max(1, args.trials), seed=args.seed)
    print("\nResults")
    print(f"  Trials:         {res['trials']}")
    print(f"  Win rate:       {res['win_rate']*100:.1f}%")
    print(f"  Avg rounds:     {res['avg_rounds']:.2f} (median {res['median_rounds']:.0f}, min {res['min_rounds']}, max {res['max_rounds']})")
    print(f"  Avg boss HP ⬇  {res['avg_boss_hp_left']:.1f}")
    print(f"  Avg survivors:  {res['avg_survivors']:.2f}")

    # Quick tuning hints
    target_wr_low, target_wr_high = 0.35, 0.65
    if res["win_rate"] > target_wr_high:
        print("\nHint: Too easy → increase boss DEF (reduces player DPR), then HP if needed; "
              "or increase ATK to raise player attrition.")
    elif res["win_rate"] < target_wr_low:
        print("\nHint: Too hard → reduce boss DEF (increase player DPR), then ATK if needed; "
              "or reduce HP to shorten fights.")

if __name__ == "__main__":
    main()