import json, os, time

COOLDOWNS_FILE = "data/cooldowns.json"

command_cooldowns = {
    "scan": 60,           # 1 minute
    "work": 180,          # 3 minutes
    "research": 600,      # 10 minutes
    "explore": 3600,      # 1 hour
    "daily": 86400,       # 24 hours
    "weekly": 604800,     # 7 days
    "lootbox": 10800,     # 3 hours
    "quest": 10800,        # 3 hours
    "bossfight": 43200,    # 12 hours
    "ship refit": 28800         # 8 hours
}

if os.path.exists(COOLDOWNS_FILE):
    with open(COOLDOWNS_FILE, "r") as f:
        active_cooldowns = json.load(f)
else:
    active_cooldowns = {}

def save_cooldowns():
    with open(COOLDOWNS_FILE, "w", encoding="utf-8") as f:
        json.dump(active_cooldowns, f, indent=4)

def set_cooldown(user_id, command, expires_at, username=None):
    uid = str(user_id)
    if uid not in active_cooldowns:
        active_cooldowns[uid] = {"username": username or f"user_{uid}", "cooldowns": {}}
    active_cooldowns[uid]["username"] = username or f"user_{uid}"
    active_cooldowns[uid]["cooldowns"][command] = expires_at
    save_cooldowns()

def get_cooldown(user_id, command):
    uid = str(user_id)
    user_data = active_cooldowns.get(uid, {})
    cooldowns = user_data.get("cooldowns", {})
    return cooldowns.get(command, 0)

# NEW: humanize durations for consistent messages
def _humanize(seconds: int) -> str:
    seconds = int(max(0, seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)

# NEW: get remaining seconds for a user's command
def get_remaining_cooldown(user_id, command) -> int:
    now = int(time.time())
    exp = int(get_cooldown(user_id, command) or 0)
    return max(0, exp - now)

# NEW: check-only helper (does not set cooldown)
async def check_cooldown_only(ctx, command: str) -> bool:
    remaining = get_remaining_cooldown(ctx.author.id, command)
    if remaining > 0:
        await ctx.send(f"⏳ You must wait {_humanize(remaining)} before using `{command}` again.")
        return False
    return True

async def check_and_set_cooldown(ctx, command, cooldown_duration):
    """Check if a command is on cooldown and set a new cooldown if not."""
    user_id = str(ctx.author.id)
    username = ctx.author.name
    now = int(time.time())

    cooldown_expires = get_cooldown(user_id, command)
    if now < cooldown_expires:
        remaining = cooldown_expires - now
        # CHANGED: humanized message
        await ctx.send(f"⏳ You must wait {_humanize(remaining)} before using `{command}` again.")
        return False

    set_cooldown(user_id, command, now + cooldown_duration, username)
    return True
