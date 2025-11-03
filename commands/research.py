import discord
from discord.ext import commands
import random
import asyncio
from typing import Tuple, Optional, List, Dict
from core.decorators import requires_profile, requires_oxygen
from core.shared import load_json
from core.players import save_profile
from core.constants import PLANETS_FILE, RESEARCH_FILE, ENEMIES_FILE, ITEMS_FILE  # CHANGED
from core.cooldowns import command_cooldowns, check_and_set_cooldown
from core.guards import set_lock, clear_lock, require_no_lock
from core.rewards import apply_rewards
from systems.crew_sys import maybe_spawn_crew
from systems.raids import load_state, save_state, charge_battery


# Canonical first-tier materials for lab training
LAB_MATS = ["plasteel", "circuit", "plasma", "biofiber"]
# Known ship types
SHIP_TYPES = ["frigate", "monitor", "dreadnought", "freighter", "outrider"]

def _resolve_item_id_and_name(items_data: dict, wanted_name: str) -> Tuple[str, str]:
    wn = (wanted_name or "").strip().lower()
    if not isinstance(items_data, dict):
        return wn, wanted_name.capitalize()
    for cat, items in items_data.items():
        if not isinstance(items, dict):
            continue
        for iid, meta in items.items():
            nm = (meta.get("name") or "").strip().lower()
            if nm == wn:
                return str(iid), meta.get("name", wanted_name.capitalize())
    return wn, wanted_name.capitalize()

def _inv_count(player: dict, item_key: str) -> int:
    inv = (player.get("inventory") or {})
    return int(inv.get(str(item_key), 0) or 0)

def _get_ship_type(player: dict) -> Optional[str]:
    ship = (player.get("ship") or {})
    if not ship.get("owned"):
        return None
    t = (ship.get("type") or "").strip().lower()
    return t if t else None

def _enemies_for_planet(enemies_data: dict, planet_id: int) -> List[dict]:
    if not isinstance(enemies_data, dict):
        return []
    # Support shape A: { "1": [ {...}, ... ], "2": [ ... ] }
    if str(planet_id) in enemies_data and isinstance(enemies_data[str(planet_id)], list):
        return [e for e in enemies_data[str(planet_id)] if isinstance(e, dict)]
    # Shape B: flat dict { "enemy_id": { name, planets:[...]/min_planet/max_planet, ... } }
    present = []
    for _, e in enemies_data.items():
        if not isinstance(e, dict):
            continue
        ps = e.get("planets")
        if isinstance(ps, list) and any(int(p) == int(planet_id) for p in ps):
            present.append(e)
            continue
        minp = e.get("min_planet"); maxp = e.get("max_planet")
        if isinstance(minp, int) or isinstance(maxp, int):
            lo = int(minp or 1); hi = int(maxp or 999)
            if lo <= planet_id <= hi:
                present.append(e)
    return present

def _enemies_not_on_planet(enemies_data: dict, planet_id: int) -> List[dict]:
    if not isinstance(enemies_data, dict):
        return []
    present_set = set()
    for e in _enemies_for_planet(enemies_data, planet_id):
        nm = (e.get("name") or "").lower()
        if nm:
            present_set.add(nm)
    others = []
    # Collect all distinct enemies not present
    for _, e in enemies_data.items():
        if isinstance(e, list):
            for ee in e:
                if not isinstance(ee, dict): continue
                nm = (ee.get("name") or "").lower()
                if nm and nm not in present_set:
                    others.append(ee)
        elif isinstance(e, dict):
            nm = (e.get("name") or "").lower()
            if nm and nm not in present_set:
                others.append(e)
    # unique by name
    seen = set(); uniq = []
    for e in others:
        nm = (e.get("name") or "").lower()
        if nm and nm not in seen:
            seen.add(nm)
            uniq.append(e)
    return uniq

def _pick_distractors(all_enemies: List[dict], count: int) -> List[str]:
    pool = [(e.get("name") or "").strip() for e in all_enemies if isinstance(e, dict) and e.get("name")]
    pool = [p for p in pool if p]
    random.shuffle(pool)
    return pool[:count]

def generate_lab_question(player: dict, items_data: dict) -> Optional[dict]:
    # Pick a random first-tier mat; resolve to id and nice name
    base_name = random.choice(LAB_MATS)
    item_id, item_name = _resolve_item_id_and_name(items_data, base_name)
    # Random threshold biased around current count
    owned = _inv_count(player, item_id)
    # Pick threshold around owned to avoid trivial answers
    if owned <= 2:
        threshold = random.randint(1, 4)
    else:
        threshold = max(1, int(round(owned * random.uniform(0.5, 1.5))))
    has_more = owned > threshold
    correct = 1 if has_more else 2  # 1-based index into ["Yes", "No"]
    return {
        "title": "🧪 Training in the Lab",
        "question": f"Do you have more than {threshold} {item_name} in your inventory?",
        "choices": ["Yes", "No"],
        "correct": correct,
        "xp_reward": random.randint(15, 25)
    }

def generate_field_question(player: dict, enemies_data: dict) -> Optional[dict]:
    planet_id = int(player.get("current_planet") or player.get("max_unlocked_planet", 1))
    present = _enemies_for_planet(enemies_data, planet_id)
    if not present:
        return None
    correct_enemy = random.choice(present)
    correct_name = correct_enemy.get("name", "Unknown")
    distractor_pool = _enemies_not_on_planet(enemies_data, planet_id)
    distractor_names = _pick_distractors(distractor_pool, 3)
    if len(distractor_names) < 3:
        return None
    choices = distractor_names + [correct_name]
    random.shuffle(choices)
    correct_index = choices.index(correct_name) + 1  # 1-based
    return {
        "title": "🛰️ Training in the Field",
        "question": "Which enemy can be found on your current planet?",
        "choices": choices,
        "correct": correct_index,
        "xp_reward": random.randint(20, 35)
    }

def generate_ship_question(player: dict) -> Optional[dict]:
    stype = _get_ship_type(player)
    if not stype:
        return None
    # Build MCQ with 1 correct + 3 other random types
    others = [t for t in SHIP_TYPES if t != stype]
    random.shuffle(others)
    picks = others[:3] + [stype]
    random.shuffle(picks)
    pretty = [p.title() for p in picks]
    correct_index = picks.index(stype) + 1
    return {
        "title": "🚀 Training on the Ship",
        "question": "What ship type do you have?",
        "choices": pretty,
        "correct": correct_index,
        "xp_reward": random.randint(18, 30)
    }

def generate_dynamic_question(player: dict) -> Tuple[Optional[dict], dict]:
    """Return (question_dict_or_none, context_data)."""
    items_data = load_json(ITEMS_FILE) or {}
    enemies_data = load_json(ENEMIES_FILE) or {}
    generators = [lambda: generate_lab_question(player, items_data),
                  lambda: generate_field_question(player, enemies_data)]
    # Ship question only if eligible
    if _get_ship_type(player):
        generators.append(lambda: generate_ship_question(player))
    random.shuffle(generators)
    for g in generators:
        q = g()
        if q:
            return q, {"items_data": items_data, "enemies_data": enemies_data}
    return None, {"items_data": items_data, "enemies_data": enemies_data}

class Research(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="research", aliases=["res"])
    @requires_profile()
    @requires_oxygen(5)
    @require_no_lock()
    async def research(self, ctx):
        if not await check_and_set_cooldown(ctx, "research", command_cooldowns.get("research", 60)):
            return

        player = ctx.player

        # Try dynamic question first; fallback to static pool
        dyn_q, _ctx = generate_dynamic_question(player)
        data = load_json(RESEARCH_FILE) or {}
        static_pool = data.get("questions", []) or []

        if dyn_q:
            question_meta = dyn_q
        elif static_pool:
            q = random.choice(static_pool)
            # Normalize static to our expected keys
            question_meta = {
                "title": "🧪 Research",
                "question": q.get("question", "Answer this question:"),
                "choices": q.get("choices", []),
                "correct": int(q.get("answer", -1)),
                "xp_reward": int(q.get("xp_reward", 10)),
            }
        else:
            await ctx.send("⚠️ No research questions available.")
            return

        choices = question_meta.get("choices", [])
        if not choices:
            await ctx.send("⚠️ Invalid question format.")
            return

        # Detect yes/no style questions (matches substrings like 'yes', 'no' in choices)
        def _yn_index(opts: List[str], needle: str) -> Optional[int]:
            for i, opt in enumerate(opts):
                if needle in opt.strip().lower():
                    return i + 1  # 1-based
            return None
        yes_idx = _yn_index(choices, "yes")
        no_idx = _yn_index(choices, "no")
        is_yesno = yes_idx is not None and no_idx is not None

        # Lock FIRST to avoid gaps where other commands can slip through
        set_lock(str(ctx.author.id), lock_type="research", allowed={"cancel"}, note="Research question")

        try:
            # Render prompt
            title = question_meta.get("title", "🧪 Research")
            choices_text = "\n".join([f"{idx+1}. {opt}" for idx, opt in enumerate(choices)])
            hint = " Type yes/no (or y/n) or reply with the option number." if is_yesno else " Reply with the option number."
            await ctx.send(
                f"{title}\n{question_meta['question']}\n\n{choices_text}\n\n"
                f"⏳ You have **15 seconds** to answer!{hint}"
            )

            def check(m):
                if m.author.id != ctx.author.id or m.channel != ctx.channel:
                    return False
                content = m.content.strip().lower()
                if content.isdigit():
                    return True
                if is_yesno and content in {"yes", "y", "no", "n"}:
                    return True
                return False

            try:
                ans_msg = await ctx.bot.wait_for("message", timeout=15.0, check=check)
            except asyncio.TimeoutError:
                await ctx.send("⌛ Time’s up! Research failed. No XP awarded.")
                return

            # Parse answer
            content = ans_msg.content.strip().lower()
            if content.isdigit():
                try:
                    answer = int(content)
                except ValueError:
                    answer = -1
            elif is_yesno:
                if content in {"yes", "y"}:
                    answer = yes_idx
                elif content in {"no", "n"}:
                    answer = no_idx
                else:
                    answer = -1
            else:
                answer = -1

            correct_answer = int(question_meta.get("correct", -1))

            if 1 <= answer <= len(choices) and answer == correct_answer:
                # Base XP: per-question reward; progression scaling handled by providers (sector/ship/etc.)
                xp_base = int(question_meta.get("xp_reward", 10))

                res = apply_rewards(
                    player,
                    {"xp": xp_base},
                    ctx_meta={"command": "research"},
                    tags=["research"]
                )

                out = f"✅ Correct! You’ve earned ⭐ {res['applied']['xp']} XP."
                if res.get("xp_result", {}).get("leveled_up"):
                    out += f" 🎉 Level up! Now Level {player['level']}."
                await ctx.send(out)
            else:
                # Show correct choice text
                correct_txt = choices[correct_answer - 1] if 1 <= correct_answer <= len(choices) else "N/A"
                await ctx.send(
                    f"❌ Your experiment failed! The correct answer was `{correct_txt}`.\n"
                    "No XP awarded (cooldown still applies)."
                )

            # Charge raid battery
            state = load_state()
            charge_battery(state, str(ctx.author.id), "research")
            save_state(state)

            save_profile(ctx.author.id, player)
        finally:
            clear_lock(str(ctx.author.id))

        await maybe_spawn_crew(ctx, source="research")

    @commands.command(name="cancel", aliases=["rcancel", "researchcancel"])
    @requires_profile()
    async def research_cancel(self, ctx):
        clear_lock(str(ctx.author.id))
        await ctx.send(f"{ctx.author.mention} canceled their research attempt.")

async def setup(bot):
    await bot.add_cog(Research(bot))
