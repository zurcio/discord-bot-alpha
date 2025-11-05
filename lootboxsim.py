import argparse
import collections
import csv
import math
import random
from typing import Dict, Tuple, List

from core.shared import load_json
from core.constants import ITEMS_FILE
from systems.lootboxes import generate_lootbox_rewards

TIERS = ["common", "uncommon", "rare", "mythic", "legendary"]

def classify_item(item_id: str, items_data: dict) -> str:
    mats = items_data.get("materials", {}) or {}
    drops = items_data.get("drops", {}) or {}
    if item_id in mats:
        return "material"
    if item_id in drops:
        return "drop"
    # fallback categories based on known IDs (e.g., lootboxes or gear)
    if item_id in {"300","301","302","303","304"}:
        return "lootbox"
    try:
        n = int(item_id)
        if 100 <= n <= 199:
            return "weapon"
        if 200 <= n <= 299:
            return "armor"
    except Exception:
        pass
    return "other"

def material_family(item_id: str) -> Tuple[str, str]:
    """
    For material ids like 'plasteel', 'plasteel_sheet', returns ('plasteel','').
    For 'plasteel_bar' returns ('plasteel','bar'). For non-materials returns ('','').
    """
    if "_" in item_id:
        base, suffix = item_id.split("_", 1)
        return base, suffix
    return item_id, ""

def summarize(tier: str, totals: Dict[str, int], hits: Dict[str, int], trials: int, items_data: dict) -> str:
    mats = items_data.get("materials", {}) or {}
    drops = items_data.get("drops", {}) or {}
    # Totals by class
    total_qty = sum(totals.values())
    mat_qty = sum(q for i, q in totals.items() if i in mats)
    drop_qty = sum(q for i, q in totals.items() if i in drops)

    # Per-open averages
    avg_total = total_qty / trials
    avg_mats = mat_qty / trials
    avg_drops = drop_qty / trials

    # Top items by average qty per open
    top_items = sorted(totals.items(), key=lambda kv: (-kv[1]/trials, kv[0]))[:15]

    lines = []
    lines.append(f"Tier: {tier} | Trials: {trials}")
    lines.append(f"Avg items per open (qty): {avg_total:.3f}  | materials {avg_mats:.3f}  | drops {avg_drops:.3f}")
    lines.append("")
    lines.append("Top items (avg qty per open | hit rate):")
    for item_id, total in top_items:
        avg = total / trials
        hr = (hits.get(item_id, 0) / trials) * 100.0
        cls = classify_item(item_id, items_data)
        # prefer name if present
        name = None
        if cls == "material":
            name = (mats.get(item_id) or {}).get("name")
        elif cls == "drop":
            name = (drops.get(item_id) or {}).get("name")
        label = f"{item_id}" + (f" ({name})" if name else "")
        lines.append(f"- {label:<32} {avg:>7.4f}  | {hr:>6.2f}%  [{cls}]")
    return "\n".join(lines)

def write_csv(path: str, tier: str, totals: Dict[str, int], hits: Dict[str, int], trials: int, items_data: dict):
    rows: List[Dict] = []
    for item_id, total in totals.items():
        avg = total / trials
        hr = hits.get(item_id, 0) / trials
        cls = classify_item(item_id, items_data)
        # name if available
        name = None
        if cls == "material":
            name = (items_data.get("materials", {}) or {}).get(item_id, {}).get("name")
        elif cls == "drop":
            name = (items_data.get("drops", {}) or {}).get(item_id, {}).get("name")
        fam, suf = ("","")
        if cls == "material":
            fam, suf = material_family(item_id)
        rows.append({
            "tier": tier,
            "item_id": item_id,
            "name": name or "",
            "class": cls,
            "family": fam,
            "suffix": suf,
            "total_qty": total,
            "avg_qty_per_open": avg,
            "hit_rate": hr,
        })
    # sort by avg desc
    rows.sort(key=lambda r: (-r["avg_qty_per_open"], r["item_id"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                           ["tier","item_id","name","class","family","suffix","total_qty","avg_qty_per_open","hit_rate"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

def run_trials_for_tier(tier: str, trials: int, unlocked_planet: int, seed: int | None) -> Tuple[Dict[str,int], Dict[str,int]]:
    rng = random.Random(seed)
    items_data = load_json(ITEMS_FILE) or {}
    player = {"max_unlocked_planet": unlocked_planet}

    totals: Dict[str, int] = collections.defaultdict(int)
    hits: Dict[str, int] = collections.defaultdict(int)

    for _ in range(trials):
        # systems.lootboxes uses random module directly; we still set seed for reproducibility at the script level
        rewards = generate_lootbox_rewards(player, tier, items_data)
        # accumulate totals and hits
        for item_id, qty in rewards.items():
            totals[item_id] += int(qty)
        # hits: an item appears in this open if qty > 0
        for item_id in rewards.keys():
            hits[item_id] += 1

    return totals, hits

def main():
    ap = argparse.ArgumentParser(description="Lootbox Monte Carlo simulator (no Discord)")
    ap.add_argument("--tier", type=str, default="all", help="Tier to test: common|uncommon|rare|mythic|legendary|all")
    ap.add_argument("--trials", type=int, default=10000, help="Trials per tier (box opens)")
    ap.add_argument("--planet", type=int, default=6, help="Simulated player max_unlocked_planet")
    ap.add_argument("--seed", type=int, default=None, help="Optional RNG seed (script-level)")
    ap.add_argument("--csv", type=str, default=None, help="Optional CSV output path (use {tier} placeholder to split per tier)")
    args = ap.parse_args()

    items_data = load_json(ITEMS_FILE) or {}

    tiers = TIERS if args.tier.lower() == "all" else [args.tier.lower()]
    for t in tiers:
        if t not in TIERS:
            print(f"Skipping unknown tier '{t}'. Valid: {', '.join(TIERS)}")
            continue
        totals, hits = run_trials_for_tier(t, max(1, args.trials), max(1, args.planet), args.seed)
        print("=" * 72)
        print(summarize(t, totals, hits, max(1, args.trials), items_data))
        if args.csv:
            # allow per-tier files using placeholder
            path = args.csv.replace("{tier}", t)
            write_csv(path, t, totals, hits, max(1, args.trials), items_data)
            print(f"(CSV) Wrote: {path}")

if __name__ == "__main__":
    main()