from typing import Dict, Optional

def update_quest_progress_for_materials(player: Dict, item_id: str, qty: int) -> bool:
    """
    Increment progress for active material-collection quests.
    Accepts either:
      - type: 'work' or 'collect_materials'
      - target keys: target_item_id, target, material_id, material, target_name, material_name
    Matches are case-insensitive.
    """
    quest = player.get("active_quest")
    if not quest:
        return False

    qtype = str(quest.get("type", "")).lower()
    if qtype not in {"work", "collect_materials"}:
        return False

    if str(quest.get("target_type", "material")).lower() not in {"material", ""}:
        return False

    provided = str(item_id).strip().lower()
    candidates = []
    for k in ("target_item_id", "target", "material_id", "material", "target_name", "material_name"):
        v = quest.get(k)
        if v is not None:
            v = str(v).strip().lower()
            if v:
                candidates.append(v)

    if provided not in set(candidates):
        return False

    qty = int(qty or 0)
    if qty <= 0:
        return False

    quest["progress"] = int(quest.get("progress", 0)) + qty
    if quest["progress"] >= int(quest.get("goal", 0)):
        quest["completed"] = True

    player["active_quest"] = quest
    return bool(quest.get("completed", False))

def update_quest_progress_for_enemy_kill(player: Dict, enemy_id: str, source: str) -> bool:
    """
    Increment progress for defeat quests.
    - type: 'defeat_scan' requires source == 'scan'
    - type: 'defeat_explore' requires source == 'explore'
    Matches by enemy_id string.
    """
    quest = player.get("active_quest")
    if not quest:
        return False
    qtype = str(quest.get("type", "")).lower()
    src = str(source or "").lower()
    if qtype not in {"defeat_scan", "defeat_explore"}:
        return False
    if qtype == "defeat_scan" and src != "scan":
        return False
    if qtype == "defeat_explore" and src != "explore":
        return False

    target_eid = str(quest.get("enemy_id") or "").strip()
    if not target_eid:
        return False
    if str(enemy_id).strip() != target_eid:
        return False

    quest["progress"] = int(quest.get("progress", 0)) + 1
    if quest["progress"] >= int(quest.get("goal", 0)):
        quest["completed"] = True
    player["active_quest"] = quest
    return bool(quest.get("completed", False))

def update_quest_progress_for_gambling(player: Dict, net_win_scrap: int) -> bool:
    """
    Increment progress for 'gamble_win' quests.
    Only positive net winnings count toward progress.
    """
    quest = player.get("active_quest")
    if not quest:
        return False
    if str(quest.get("type", "")).lower() != "gamble_win":
        return False
    amt = int(net_win_scrap or 0)
    if amt <= 0:
        return False
    quest["progress"] = int(quest.get("progress", 0)) + amt
    if quest["progress"] >= int(quest.get("goal", 0)):
        quest["completed"] = True
    player["active_quest"] = quest
    return bool(quest.get("completed", False))

def update_quest_progress_for_trade(player: Dict) -> bool:
    """
    Completes 'do_trade' quests when any valid trade is made.
    Increments by 1; goal is typically 1.
    """
    quest = player.get("active_quest")
    if not quest:
        return False
    if str(quest.get("type", "")).lower() != "do_trade":
        return False

    quest["progress"] = int(quest.get("progress", 0)) + 1
    if quest["progress"] >= int(quest.get("goal", 0) or 1):
        quest["completed"] = True
    player["active_quest"] = quest
    return bool(quest.get("completed", False))


def update_quest_progress_for_crafting(player: Dict, crafted_item_id: str, qty: int) -> bool:
    """
    Increment progress for 'craft_material' quests when the specified recipe/material is crafted.
    Matches by target_item_id/recipe_id string; qty is number of outputs crafted.
    """
    quest = player.get("active_quest")
    if not quest:
        return False
    if str(quest.get("type", "")).lower() != "craft_material":
        return False

    target = (quest.get("target_item_id")
              or quest.get("recipe_id")
              or quest.get("target"))
    if not target:
        return False

    if str(crafted_item_id) != str(target):
        return False

    q = int(qty or 0)
    if q <= 0:
        return False

    quest["progress"] = int(quest.get("progress", 0)) + q
    if quest["progress"] >= int(quest.get("goal", 0) or 1):
        quest["completed"] = True
    player["active_quest"] = quest
    return bool(quest.get("completed", False))


def craft_progress_line_if_applicable(player: Dict, crafted_item_id: str) -> Optional[str]:
    """
    If the active quest is a craft_material quest that targets the given crafted_item_id,
    return a short one-line progress string like:
      "Quest: Craft <name> — 3/10" or "Quest: Craft <name> — 10/10 ✅".
    Otherwise return None.
    """
    quest = player.get("active_quest") or {}
    if str(quest.get("type", "")).lower() != "craft_material":
        return None

    target = (quest.get("target_item_id")
              or quest.get("recipe_id")
              or quest.get("target"))
    if not target:
        return None

    if str(crafted_item_id) != str(target):
        return None

    name = (quest.get("target_name")
            or quest.get("material_name")
            or quest.get("name")
            or str(target))
    prog = int(quest.get("progress", 0) or 0)
    goal = int(quest.get("goal", 0) or 1)
    done = bool(quest.get("completed", False))
    badge = " ✅" if done else ""
    return f"Quest: Craft {name} — {prog}/{goal}{badge}"
