import time
from typing import Optional, Set, Dict
from discord.ext import commands

# Per-user timestamps for anti-spam
_last_cmd_ts: Dict[str, float] = {}
_last_warn_ts: Dict[str, float] = {}

# Per-user pending locks
# { user_id: { "type": str, "created": float, "allowed": set[str], "note": str } }
_user_locks: Dict[str, Dict] = {}

GUARD_SPAM_SECONDS = 1.0
WARN_SPAM_SECONDS = 2.0
EXEMPT_FROM_RATELIMIT = {"cancel"}  # allow quick cancel during interactive flows

# ---------- Lock helpers ----------
def set_lock(user_id: str, lock_type: str, allowed: Optional[Set[str]] = None, note: str = ""):
    _user_locks[str(user_id)] = {
        "type": lock_type,
        "created": time.time(),
        "allowed": set(allowed or set()),
        "note": note or lock_type,
    }

def clear_lock(user_id: str):
    _user_locks.pop(str(user_id), None)

def get_lock(user_id: str) -> Optional[Dict]:
    return _user_locks.get(str(user_id))

def has_lock(user_id: str) -> bool:
    return str(user_id) in _user_locks

# ---------- Decorator you can add on commands to enforce no-lock ----------
def require_no_lock(extra_allowed: Optional[Set[str]] = None):
    extra_allowed = set(extra_allowed or set())
    async def predicate(ctx: commands.Context) -> bool:
        uid = str(ctx.author.id)
        lock = get_lock(uid)
        if not lock:
            return True
        cmd_name = (ctx.command.name if ctx.command else "").lower()
        allowed = set(lock["allowed"]) | extra_allowed
        if cmd_name in allowed:
            return True
        # Send a concise, contextual hint
        if lock["type"] == "research":
            hint = "Finish your research first (reply with the option number or use `!cancel`)."
        elif lock["type"] == "bossfight":
            hint = "You’re in a bossfight. Other commands are disabled until it ends."
        else:
            hint = f"Pending action: {lock['note']}. Complete it first."
        try:
            await ctx.send(f"⏳ {hint}")
        except Exception:
            pass
        return False
    return commands.check(predicate)

# ---------- Global guard check ----------
async def global_command_guard(ctx: commands.Context) -> bool:
    uid = str(ctx.author.id)
    now = time.monotonic()
    cmd_name = (ctx.command.name if ctx.command else "").lower()

    # 1) Anti-spam (skip for exempt quick-reply commands)
    if cmd_name not in EXEMPT_FROM_RATELIMIT:
        last = _last_cmd_ts.get(uid, 0.0)
        if now - last < GUARD_SPAM_SECONDS:
            last_warn = _last_warn_ts.get(uid, 0.0)
            if now - last_warn >= WARN_SPAM_SECONDS:
                _last_warn_ts[uid] = now
                try:
                    await ctx.send(f"{ctx.author.mention} slow down — wait a second between commands.")
                except Exception:
                    pass
            return False

    # 2) Pending locks
    lock = _user_locks.get(uid)
    if lock:
        allowed = lock["allowed"]
        if cmd_name not in allowed:
            last_warn = _last_warn_ts.get(uid, 0.0)
            if now - last_warn >= WARN_SPAM_SECONDS:
                _last_warn_ts[uid] = now
                try:
                    if lock["type"] == "research":
                        hint = "Finish your research first (reply with the option number or use `!cancel`)."
                    elif lock["type"] == "bossfight":
                        hint = "You’re in a bossfight. Other commands are disabled until it ends."
                    else:
                        hint = f"Pending action: {lock['note']}. Complete it first."
                    await ctx.send(f"⏳ {hint}")
                except Exception:
                    pass
            return False

    # Passed guard; record timestamp (only for non-exempt)
    if cmd_name not in EXEMPT_FROM_RATELIMIT:
        _last_cmd_ts[uid] = now
    return True

async def setup(bot: commands.Bot):
    # Register as a global check
    bot.add_check(global_command_guard)