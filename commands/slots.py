import asyncio
import math
import random
import discord
from discord.ext import commands
from core.decorators import requires_profile
from core.guards import require_no_lock, set_lock, clear_lock
from core.players import load_profile, save_profile, get_scrap, set_scrap
from core.shared import load_json
from core.quest_progress import update_quest_progress_for_gambling
from systems.ship_sys import derive_ship_effects
from core.skills_hooks import award_skill
from core.constants import SHOP_FILE

# Reels and payouts (3-of-a-kind wins; 2-of-a-kind small return)
SYMBOLS = [
    {"key": "cherry",  "emoji": "🍒", "weight": 35, "payout": 2},
    {"key": "lemon",   "emoji": "🍋", "weight": 25, "payout": 3},
    {"key": "bell",    "emoji": "🔔", "weight": 18, "payout": 5},
    {"key": "star",    "emoji": "⭐", "weight": 12, "payout": 10},
    {"key": "seven",   "emoji": "7️⃣", "weight": 6,  "payout": 25},
    {"key": "diamond", "emoji": "💎", "weight": 3,  "payout": 50},
    {"key": "skull",   "emoji": "☠️", "weight": 1,  "payout": 0, "trap": True},
]
WEIGHTS = [s["weight"] for s in SYMBOLS]

# Jackpot tuning
BASE_JACKPOT_RATE = 0.0002
JACKPOT_CAP = 0.01

# Ultra-rare gear drop chance
SUPER_DROP_CHANCE = 0.00005

# Gear ID ranges
GEAR_WEAPON_RANGE = (100, 109)
GEAR_ARMOR_RANGE  = (200, 209)

# Trap event
TRAP_TRIGGER_CHANCE = 0.015
TRAP_RESPONSE_SECONDS = 3
TRAP_DAMAGE_HP = 5

LOOTBOX_IDS = {
    "common": "300",
    "uncommon": "301",
    "rare": "302",
    "mythic": "303",
    "legendary": "304",
    "solar": "305"
}

def _choose_symbol(rng: random.Random) -> int:
    total = sum(WEIGHTS)
    roll = rng.randint(1, total)
    cum = 0
    for i, w in enumerate(WEIGHTS):
        cum += w
        if roll <= cum:
            return i
    return len(SYMBOLS) - 1

def _format_reels(idxs):
    return " | ".join(SYMBOLS[i]["emoji"] for i in idxs)

def _resolve_lootbox_prices() -> dict:
    shop = load_json(SHOP_FILE) or {}
    loot = (shop.get("lootbox") or {})
    id_to_price = {}
    if isinstance(loot, dict):
        for k, v in loot.items():
            try:
                iid = str(v.get("item_id") or k)
                id_to_price[iid] = int(v.get("price", 0) or 0)
            except Exception:
                continue
    return {tier: id_to_price.get(iid, 0) for tier, iid in LOOTBOX_IDS.items()}

def _add_inventory(profile: dict, item_id: str, qty: int = 1):
    inv = profile.get("inventory", {}) or {}
    inv[str(item_id)] = int(inv.get(str(item_id), 0) or 0) + int(qty)
    profile["inventory"] = inv

def _pick_super_gear_id(rng: random.Random) -> str:
    if rng.random() < 0.5:
        base, hi = GEAR_WEAPON_RANGE
    else:
        base, hi = GEAR_ARMOR_RANGE
    iid = rng.randint(base, hi)
    return str(iid)

def _gear_quality_label(item_id: str) -> tuple[str, str]:
    try:
        d = int(item_id) % 10
    except Exception:
        d = 0
    if d in (1, 2):
        return ("good", "🟢")
    if 3 <= d <= 6:
        return ("great", "🔵")
    if d in (7, 8):
        return ("mythical", "🟣")
    if d == 9:
        return ("legendary", "🟠")
    return ("good", "🟢")

def _compute_payout_and_events(bet: int, reels: list[int], rng: random.Random):
    a, b, c = reels
    payout = 0
    trap = False
    triple = (a == b == c)
    if triple and SYMBOLS[a].get("trap"):
        trap = True
    elif triple:
        payout = bet * SYMBOLS[a]["payout"]
    else:
        if a == b or b == c or a == c:
            idx = b if (a == b or b == c) else a
            sym = SYMBOLS[idx]
            if not sym.get("trap") and sym["key"] in {"cherry", "lemon", "bell", "star"}:
                payout = math.floor(bet * 1.2)
    if not trap and rng.random() < TRAP_TRIGGER_CHANCE:
        trap = True
    return payout, trap

def _sync_ctx(ctx, prof: dict, keys=("Scrap", "inventory", "health", "Health", "hp", "HP")):
    """
    Best-effort sync of mutated fields into ctx.player so any post-command save won't revert changes.
    """
    p = getattr(ctx, "player", None)
    if not isinstance(p, dict):
        return
    for k in keys:
        if k in prof:
            p[k] = prof[k]

class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="slots", help="Spin the slots. Usage: !slots <bet|all|half>")
    @requires_profile()
    @require_no_lock()
    async def slots(self, ctx, bet: str = None):
        rng = random.Random()
        uid = str(ctx.author.id)

        prof = load_profile(uid) or {}
        funds = get_scrap(prof)
        if funds <= 0:
            await ctx.send(f"{ctx.author.mention} You have no Scrap.")
            return

        if not bet:
            await ctx.send(f"Usage: !slots <bet|all|half>. You have {funds:,} Scrap.")
            return
        bet_lc = bet.strip().lower()
        if bet_lc == "all":
            wager = funds
        elif bet_lc == "half":
            wager = max(1, funds // 2)
        else:
            try:
                wager = int(bet_lc)
            except ValueError:
                await ctx.send("Bet must be a number, 'all', or 'half'.")
                return
        MIN_BET = 10
        MAX_BET = max(100000, funds)
        wager = max(MIN_BET, min(wager, funds, MAX_BET))
        if wager <= 0:
            await ctx.send("Insufficient Scrap for that bet.")
            return

        set_lock(uid, lock_type="slots", allowed=set(), note="slots")
        try:
            prof = load_profile(uid) or {}
            funds = get_scrap(prof)
            if funds < wager:
                await ctx.send("Insufficient Scrap.")
                return

            # Deduct bet upfront
            set_scrap(prof, funds - wager)
            save_profile(uid, prof)
            _sync_ctx(ctx, prof, keys=("Scrap",))  # keep ctx.player in sync

            # Spin animation
            msg = await ctx.send("🎰 Spinning...")
            await asyncio.sleep(0.6)
            r1 = _choose_symbol(rng)
            await msg.edit(content=f"🎰 {SYMBOLS[r1]['emoji']} | ❔ | ❔")
            await asyncio.sleep(0.6)
            r2 = _choose_symbol(rng)
            await msg.edit(content=f"🎰 {SYMBOLS[r1]['emoji']} | {SYMBOLS[r2]['emoji']} | ❔")
            await asyncio.sleep(0.6)
            r3 = _choose_symbol(rng)
            final_reels = [r1, r2, r3]
            await msg.edit(content=f"🎰 { _format_reels(final_reels) }")

            payout, trap = _compute_payout_and_events(wager, final_reels, rng)
            net = payout - wager

            # Jackpot rolls
            lootbox_prices = _resolve_lootbox_prices()
            awarded_lb: list[str] = []
            if lootbox_prices:
                for tier in ("legendary", "mythic", "rare", "uncommon", "common"):
                    price = int(lootbox_prices.get(tier, 0) or 0)
                    if price <= 0:
                        continue
                    chance = min(JACKPOT_CAP, (wager / price) * BASE_JACKPOT_RATE)
                    if rng.random() < chance:
                        awarded_lb.append(tier)
                        break

            # Ultra-rare gear drop roll
            awarded_gear_id = None
            if rng.random() < SUPER_DROP_CHANCE:
                awarded_gear_id = _pick_super_gear_id(rng)

            # Apply winnings and rewards on a fresh profile snapshot
            prof = load_profile(uid) or {}

            # Credit payout
            if payout > 0:
                set_scrap(prof, get_scrap(prof) + payout)
                # NEW: Gambler XP (flat +5 per win)
                award_skill(ctx, "gambler", 5)

            # Award lootboxes
            for tier in awarded_lb:
                iid = LOOTBOX_IDS.get(tier)
                if iid:
                    _add_inventory(prof, iid, 1)

            # Award ultra-rare gear
            if awarded_gear_id:
                _add_inventory(prof, awarded_gear_id, 1)

            # Trap
            took_damage = False
            if trap:
                await ctx.send(f"{ctx.author.mention} 💥 A trap springs! Type 'run' within {TRAP_RESPONSE_SECONDS}s!")
                def check(m: discord.Message):
                    return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id and m.content.strip().lower() == "run"
                try:
                    await self.bot.wait_for("message", timeout=TRAP_RESPONSE_SECONDS, check=check)
                    await ctx.send("🏃 You dodged it!")
                except asyncio.TimeoutError:
                    # Apply 5 HP damage; life support only prevents death
                    keys = ["health", "Health", "hp", "HP"]
                    hp_key = None
                    for k in keys:
                        if isinstance(prof.get(k), int):
                            hp_key = k
                            break
                    if hp_key:
                        cur_hp = int(prof.get(hp_key, 0) or 0)
                        new_hp = max(0, cur_hp - TRAP_DAMAGE_HP)
                        effects = derive_ship_effects(prof)
                        if bool(effects.get("life_support")) and new_hp <= 0:
                            new_hp = 1
                        prof[hp_key] = new_hp
                        took_damage = True
                        await ctx.send(f"💢 You took {TRAP_DAMAGE_HP} damage!")
                    else:
                        penalty = min(50, max(5, wager // 20))
                        set_scrap(prof, max(0, get_scrap(prof) - penalty))
                        await ctx.send(f"💢 You were rattled and dropped {penalty} Scrap!")

            if net > 0:
                update_quest_progress_for_gambling(prof, int(net))

            save_profile(uid, prof)
            _sync_ctx(ctx, prof)  # sync Scrap, inventory, and health

            # Final summary
            lines = []
            lines.append(f"{ctx.author.mention} Bet: {wager:,} Scrap")
            lines.append(f"Result: { _format_reels(final_reels) }")
            if payout > 0:
                lines.append(f"Win: +{payout:,} Scrap • 🎲 Gambler +5 XP")
            else:
                lines.append("No win.")
            if awarded_lb:
                pretty = ", ".join(t.capitalize() for t in awarded_lb)
                lines.append(f"🎁 Jackpot: {pretty} Lootbox")
            if awarded_gear_id:
                qlabel, qemoji = _gear_quality_label(awarded_gear_id)
                gear_type = "Weapon" if awarded_gear_id.startswith("1") else "Armor"
                lines.append(f"{qemoji} Ultra-rare: {qlabel.capitalize()} {gear_type} (#{awarded_gear_id})")
            if trap and took_damage:
                lines.append(f"Trap: -{TRAP_DAMAGE_HP} HP")
            await ctx.send("\n".join(lines))

        finally:
            clear_lock(uid)

async def setup(bot):
    await bot.add_cog(Slots(bot))
