import os

"""
Data directories
- DATA_DIR: packaged, read-only defaults (items.json, planets.json, etc.)
- RUNTIME_DATA_DIR: writable location for runtime state (players.json, cooldowns.json, raids.json)
    Can be overridden via env var RUNTIME_DATA_DIR (e.g., when mounting a volume in production).
"""
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RUNTIME_DATA_DIR = os.getenv("RUNTIME_DATA_DIR", DATA_DIR)

# === JSON FILES ===
PLAYERS_FILE = os.path.join(RUNTIME_DATA_DIR, "players.json")
ITEMS_FILE = os.path.join(DATA_DIR, "items.json")
SHOP_FILE = os.path.join(DATA_DIR, "shop.json")
PLANETS_FILE = os.path.join(DATA_DIR, "planets.json")
BOSSES_FILE = os.path.join(DATA_DIR, "bosses.json")
ENEMIES_FILE = os.path.join(DATA_DIR, "enemies.json")
COOLDOWNS_FILE = os.path.join(RUNTIME_DATA_DIR, "cooldowns.json")
CRAFTING_FILE = os.path.join(DATA_DIR, "crafting.json")
LOOTBOXES_FILE = os.path.join(DATA_DIR, "lootbox.json")
RESEARCH_FILE = os.path.join(DATA_DIR, "research.json")
CODES_FILE = os.path.join(DATA_DIR, "codes.json")
CREDITSHOP_FILE = os.path.join(DATA_DIR, "creditshop.json")
RECIPES_FILE = os.path.join(DATA_DIR, "recipes.json")
RAIDS_FILE = os.path.join(RUNTIME_DATA_DIR, "raids.json")

# === GAME CONSTANTS ===
DEFAULT_HEALTH = 100
DEFAULT_OXYGEN = 100
XP_PER_LEVEL = 100
SCRAP_ICON = "💳"

# === COMBAT CONSTANTS ===
BASE_ATTACK_MULT = 1.0
BASE_DEFENSE_MULT = 1.0
PLAYER_BASE_DAMAGE = 10
ENEMY_BASE_DAMAGE = 8

# === LOOTBOX CONSTANTS ===
LOOTBOX_TIERS = ["common", "uncommon", "rare", "mythic", "legendary"]
LOOTBOX_COOLDOWN = 10800  # 3 hours in seconds


# skills stuff
SKILLS_ENABLED = True
SKILLS_VERBOSE = False  # set True to log every award to console/dev channel

# Optional: dev channel id for verbose logs (set to int or None)
SKILLS_LOG_CHANNEL_ID = None

# Skills: Bank interest principal cap (only first N Scrap earns interest)
SKILLS_BANK_INTEREST_PRINCIPAL_CAP = 1_000_000_000  # 1B (tweak as needed)


# === COMMAND COOLDOWNS (centralized reference) ===
COMMAND_COOLDOWNS = {
    "scan": 60,           # 1 minute
    "work": 180,          # 3 minutes
    "research": 600,      # 10 minutes
    "explore": 3600,      # 1 hour
    "bossfight": 43200,   # 12 hours
    "daily": 86400,       # 24 hours
    "weekly": 604800,     # 7 days
    "lootbox": 10800,     # 3 hours
    "quest": 10800,        # 3 hours
    "bossfight": 43200,    # 12 hours
    "ship refit": 28800    # 8 hours
}

COMMAND_GROUPS = {
    "Play": ["scan", "work", "research", "explore"],
    "Progression": ["bossfight", "quest", "planet", "travel", "sector", "ship", "ship upgrade", "ship refit", "skills", "overcharge"],
    "Inventory": ["inventory", "equip", "tinker", "recipes", "craft", "dismantle", "use", "shop","buy", "lootbox", "open", "lootbox", "trade"],
    "Gambling": ["roulette", "slots", "race"],
    "Misc": ["commands", "ready", "daily", "weekly", "profile", "creditshop", "creditbuy", "raid", "help/info"]
}

WORK_COMMANDS = ["scavenge", "hack", "extract", "harvest"]

GROUP_EMOJIS = {
    "Play": "🚀",
    "Progression": "🌌",
    "Inventory": "🎒",
    "Gambling": "🎰",
    "Misc": "⚙️"
}

COOLDOWN_COMMANDS = {"scan", "work", "research", "explore", "lootbox", "quest", "ship refit", "daily", "weekly"}
