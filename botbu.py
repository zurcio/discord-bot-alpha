# import discord
# from discord.ext import commands
# from discord.ui import View, Button
# import json
# import os
# import random
# import math
# import time
# from datetime import timedelta, datetime
# from functools import wraps
# import asyncio   
# import traceback


# # ====================================================
# # JSON DATA HELPERS
# # ====================================================

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# PLAYERS_FILE = os.path.join(BASE_DIR, "players.json")
# COOLDOWNS_FILE = os.path.join(BASE_DIR, "cooldowns.json")
# SHOP_FILE = os.path.join(BASE_DIR, "shop.json")
# ITEMS_FILE = os.path.join(BASE_DIR, "items.json")
# ENEMIES_FILE = os.path.join(BASE_DIR, "enemies.json")
# CRAFTING_FILE = os.path.join(BASE_DIR, "crafting.json")
# PLANETS_FILE = os.path.join(BASE_DIR, "planets.json")
# RESEARCH_FILE = os.path.join(BASE_DIR, "research.json")
# BOSSES_FILE = os.path.join(BASE_DIR, "bosses.json")


# def load_json(path):
#     """Load JSON data safely from a file. Returns {} if missing or corrupt."""
#     if not os.path.exists(path):
#         return {}
#     try:
#         with open(path, "r", encoding="utf-8") as f:
#             return json.load(f)
#     except json.JSONDecodeError:
#         print(f"[json] WARNING: {path} was corrupt, resetting.")
#         return {}

# def save_json(path, data):
#     """Write JSON data safely to a file."""
#     tmp = path + ".tmp"
#     with open(tmp, "w", encoding="utf-8") as f:
#         json.dump(data, f, indent=2)
#         f.flush()
#         os.fsync(f.fileno())
#     os.replace(tmp, path)
#     print(f"[json] saved {path}")

# # ====================================================
# # DISCORD BOT SETUP
# # ====================================================

# intents = discord.Intents.default()
# intents.message_content = True  # required for !commands
# bot = commands.Bot(command_prefix=["!", "spc ",], intents=intents)

# @bot.event
# async def on_ready():
#     print(f"✅ Logged in as {bot.user}")

# @bot.event
# async def on_command_error(ctx, error):
#     if isinstance(error, commands.CommandOnCooldown):
#         # Format remaining time
#         minutes, seconds = divmod(int(error.retry_after), 60)
#         hours, minutes = divmod(minutes, 60)

#         if hours > 0:
#             time_left = f"{hours}h {minutes}m {seconds}s"
#         elif minutes > 0:
#             time_left = f"{minutes}m {seconds}s"
#         else:
#             time_left = f"{seconds}s"

#         # Reply with command name + cooldown time
#         await ctx.send(
#             f"⏳ `{ctx.command.name}` is on cooldown! Try again in **{time_left}**."
#         )
#     elif isinstance(error, commands.CommandNotFound):
#         # Optional: ignore unknown commands, or notify
#         return
#     else:
#         raise error

# # ====================================================
# # PLAYERS JSON helpers (load/save single player)
# # ====================================================
# def load_players():
#     """Load players from JSON, or create file if missing."""
#     if not os.path.exists(PLAYERS_FILE):
#         with open(PLAYERS_FILE, "w", encoding="utf-8") as f:
#             json.dump({}, f)
#         print(f"[players] created new players.json at: {PLAYERS_FILE}")

#     try:
#         with open(PLAYERS_FILE, "r", encoding="utf-8") as f:
#             return json.load(f)
#     except json.JSONDecodeError:
#         print("[players] WARNING: players.json was corrupt, resetting.")
#         return {}

# def save_players(data):
#     """Write player data safely to JSON."""
#     tmp = PLAYERS_FILE + ".tmp"
#     with open(tmp, "w", encoding="utf-8") as f:
#         json.dump(data, f, indent=2)
#         f.flush()
#         os.fsync(f.fileno())
#     os.replace(tmp, PLAYERS_FILE)
#     print(f"[players] saved {len(data)} players -> {PLAYERS_FILE}")


# # ====== Profile load/save wrappers ======
# def load_profile(user_id):
#     """Return a single player's profile dict, or None if not found."""
#     players = load_players()
#     return players.get(str(user_id))

# def save_profile(user_id, profile):
#     players = load_players()
#     players[str(user_id)] = profile
#     save_players(players)
#     print(f"[SAVE_PROFILE] {user_id} saved with level={profile.get('level')} "
#           f"hp={profile.get('health')} planet={profile.get('max_unlocked_planet')} "
#           f"inv_keys={list(profile.get('inventory', {}).keys())}")
    
#     # Debugging: show who called save_profile
#     stack = "".join(traceback.format_stack(limit=3))
#     print(f"[DEBUG] save_profile call stack:\n{stack}")


# # ====================================================
# # Level-based max helpers (flexible: accept player dict or int level)
# # ====================================================
# def get_max_health(player_or_level):
#     """Accept either a player dict or an integer level."""
#     if isinstance(player_or_level, dict):
#         level = int(player_or_level.get("level", 1))
#     else:
#         level = int(player_or_level)
#     return 100 + (level * 5)

# def get_max_oxygen(player_or_level):
#     """Accept either a player dict or an integer level."""
#     if isinstance(player_or_level, dict):
#         level = int(player_or_level.get("level", 1))
#     else:
#         level = int(player_or_level)
#     return 100 + (level * 5)

# # ===================================================
# # Combat functions
# # ===================================================

# def calculate_combat_stats(player):
#     """Return combat stats = base per level + equipped bonuses with multipliers."""
#     level = player.get("level", 1)

#     # Base scaling: +5 per level
#     base_attack = 5 * level
#     base_defense = 5 * level

#     items = load_json(ITEMS_FILE)
#     equipped = player.get("equipped", {})

#     # Start from base stats
#     attack = base_attack
#     defense = base_defense

#     # Default multipliers
#     attack_mult = 1.0
#     defense_mult = 1.0

#     # Weapon
#     weapon_id = equipped.get("weapon")
#     if weapon_id:
#         weapon = get_item_by_id(items, weapon_id)
#         if weapon:
#             attack += weapon.get("attack", 0)
#             defense += weapon.get("defense", 0)
#             attack_mult *= weapon.get("attack_mult", 1.0)
#             defense_mult *= weapon.get("defense_mult", 1.0)

#     # Armor
#     armor_id = equipped.get("armor")
#     if armor_id:
#         armor = get_item_by_id(items, armor_id)
#         if armor:
#             attack += armor.get("attack", 0)
#             defense += armor.get("defense", 0)
#             attack_mult *= armor.get("attack_mult", 1.0)
#             defense_mult *= armor.get("defense_mult", 1.0)

#     # Apply multipliers to total
#     final_attack = int(attack * attack_mult)
#     final_defense = int(defense * defense_mult)

#     return {"attack": final_attack, "defense": final_defense}


# # Get enemies for player's current planet
# def get_enemies_for_player(player):
#     """Return the dictionary of enemies for the player's current planet."""
#     planet_id = f"P{player.get('current_planet', 1)}E"
#     enemies_data = load_json(ENEMIES_FILE)
#     return enemies_data.get(planet_id, {})

# # Choose a random enemy from the available ones
# def choose_random_enemy(player, category="basic"):
#     planet_id = str(player.get("current_planet", 1))
#     enemies_data = load_json(ENEMIES_FILE).get(f"P{planet_id}E", {})

#     # Filter by category
#     valid_enemies = {k:v for k,v in enemies_data.items() if v.get("category") == category}
#     if not valid_enemies:
#         return None, None

#     enemy_key = random.choice(list(valid_enemies.keys()))
#     return enemy_key, valid_enemies[enemy_key]

# # Simulate combat between player and enemy
# def simulate_combat(player, enemy):
#     """
#     Simulate a full fight until one side dies.
#     Returns dict:
#     {
#         'player_won': True/False,
#         'enemy_hp_left': int,
#         'player_hp_left': int,
#         'rounds': int,
#         'drops': list
#     }
#     """
#     player_hp = player.get("health", get_max_health(player))
#     enemy_hp = enemy["hp"]
#     rounds = 0
#     drops = []
#     stats = calculate_combat_stats(player)

#     while player_hp > 0 and enemy_hp > 0:
#         rounds += 1

#         # Damage per round
#         player_damage = max(stats["attack"] - enemy.get("defense", 0), 1)
#         enemy_damage = max(enemy.get("attack", 0) - stats["defense"], 0)

#         enemy_hp -= player_damage
#         player_hp -= enemy_damage

#     player_won = enemy_hp <= 0 and player_hp > 0

#     # Handle drops
#     if player_won:
#         for drop in enemy.get("drops", []):
#             # 50% chance for testing
#             if random.random() < 0.02:
#                 drops.append(drop)

#     return {
#         "player_won": player_won,
#         "enemy_hp_left": max(enemy_hp, 0),
#         "player_hp_left": max(player_hp, 0),
#         "rounds": rounds,
#         "drops": drops
#     }


# # ====================================================
# # Default profile and migration helpers
# # ====================================================

# def default_profile(uid, username=None, level: int = 1):
#     """Return a full default profile dict for a user id (uid as string or int)."""
#     uid_str = str(uid)
#     lvl = int(level)
#     return {
#         "id": uid_str,
#         "username": username or f"user_{uid_str}",
#         "level": lvl,
#         "xp": 0,
#         "total_xp": 0,
#         "Scrap": 0,
#         "inventory": {},

#         # Survival (current values; max are computed dynamically)
#         "health": get_max_health(lvl),
#         "oxygen": get_max_oxygen(lvl),

#         # Equipped gear (attack/defense are NOT stored in schema anymore)
#         "equipped": {
#             "weapon": None,
#             "armor": None
#         },

#         # Progression
#         "default_planet": 1,
#         "current_planet": 1,
#         "current_sector": 1,
#         "max_unlocked_planet": 1,

#         # Last regen timestamp
#         "last_regen": int(time.time()),
#         "active_tank": None,  # id of active oxygen tank (if any)
#     }

# def migrate_players_file():
#     """Migrate players.json to remove obsolete attack/defense and old equipped_* keys."""
#     players = load_players()
#     changed = False

#     for uid, profile in players.items():
#         # Remove static attack/defense if present
#         if "attack" in profile:
#             profile.pop("attack")
#             changed = True
#         if "defense" in profile:
#             profile.pop("defense")
#             changed = True

#         # Remove old equipped_weapon/armor keys if present
#         if "equipped_weapon" in profile:
#             profile.pop("equipped_weapon")
#             changed = True
#         if "equipped_armor" in profile:
#             profile.pop("equipped_armor")
#             changed = True

#         # Ensure equipped dict exists
#         if "equipped" not in profile:
#             profile["equipped"] = {"weapon": None, "armor": None}
#             changed = True

#     if changed:
#         save_players(players)
#         print("✅ Migration complete: players.json updated.")
#     else:
#         print("ℹ️ No migration needed: players.json already up-to-date.")



# def migrate_player(player, uid, username):
#     """Migrate a single player profile in memory."""
#     changed = False

#     # Ensure equipped dict exists
#     if "equipped" not in player:
#         player["equipped"] = {"weapon": None, "armor": None}
#         changed = True

#     # Remove obsolete keys
#     for key in ["attack", "defense", "equipped_weapon", "equipped_armor"]:
#         if key in player:
#             player.pop(key)
#             changed = True

#     # Add username if missing
#     if "username" not in player:
#         player["username"] = username
#         changed = True

#     # Ensure last_regen exists
#     if "last_regen" not in player:
#         player["last_regen"] = int(time.time())
#         changed = True

#     # Ensure active_tank exists and is valid
#     if "active_tank" not in player or not isinstance(player["active_tank"], dict):
#         player["active_tank"] = None
#         changed = True
#     else:
#         # If dict exists but missing required fields, repair
#         if "id" not in player["active_tank"] or "remaining" not in player["active_tank"]:
#             player["active_tank"] = None
#             changed = True

#     return player


# def migrate_currency_to_Scrap():
#     players = load_players()
#     changed = False

#     for uid, profile in players.items():
#         if "credits" in profile:
#             profile["Scrap"] = profile.get("Scrap", 0) + profile["credits"]
#             profile.pop("credits")
#             changed = True

#     if changed:
#         save_players(players)
#         print("✅ Migration complete: credits → Scrap")
#     else:
#         print("ℹ️ No migration needed")


# # ====================================================
# # HELPER DECORATOR FOR PROFILE 
# # ====================================================
# def with_profile(auto_save=True):
#     """
#     Attach player profile to ctx.player (ensures migration), auto-saves at end (optional).
#     """
#     def decorator(func):
#         @wraps(func)
#         async def wrapper(ctx, *args, **kwargs):
#             uid = str(ctx.author.id)
#             username = ctx.author.name

#             # Load / create / migrate
#             player = load_profile(uid) or default_profile(uid, username)
#             player = migrate_player(player, uid, username)
#             player = apply_oxygen_regen(player)

#             ctx.player = player

#             # Execute command
#             result = await func(ctx, *args, **kwargs)

#             # Clamp & save if enabled
#             ctx.player["health"] = min(ctx.player.get("health", 0), get_max_health(ctx.player.get("level", 1)))
#             ctx.player["oxygen"] = min(ctx.player.get("oxygen", 0), get_max_oxygen(ctx.player.get("level", 1)))

#             if auto_save:
#                 save_profile(uid, ctx.player)

#             return result
#         return wrapper
#     return decorator


# # ====================================================
# # EXISTING PLAYER-FACING HELPERS (add_xp, update, etc.)
# # ====================================================
# def get_player(user_id, username=None):
#     """Fetch a player's profile, creating it if missing, and ensure all default fields exist."""
#     players = load_players()
#     uid = str(user_id)

#     if uid not in players:
#         players[uid] = default_profile(uid, username)
#         save_players(players)
#         print(f"[players] created profile for {players[uid]['username']} ({uid})")

#     player = players[uid]

#     # Ensure all default fields exist
#     defaults = default_profile(uid, username)
#     for key, value in defaults.items():
#         if key not in player:
#             player[key] = value

#     # Ensure inventory is always a dict
#     if not isinstance(player.get("inventory"), dict):
#         player["inventory"] = {}

#     # Save any changes (e.g., added missing fields)
#     players[uid] = player
#     save_players(players)

#     return player

# def update_player(user_id, updates: dict, username=None):
#     """Update player profile and save."""
#     players = load_players()
#     uid = str(user_id)

#     if uid not in players:
#         players[uid] = default_profile(uid, username)

#     # Safety net for old profiles
#     if not isinstance(players[uid].get("inventory"), dict):
#         players[uid]["inventory"] = {}

#     players[uid].update(updates)
#     save_players(players)
#     print(f"[players] updated profile for {uid}: {updates}")

# def add_xp(user_id, username, amount):
#     players = load_players()
#     uid = str(user_id)

#     if uid not in players:
#         get_player(user_id, username)
#         players = load_players()

#     player = players[uid]
#     player["xp"] += amount
#     player["total_xp"] = player.get("total_xp", 0) + amount  # safe update

#     leveled_up = False
#     while player["xp"] >= player["level"] * 100:
#         player["xp"] -= player["level"] * 100
#         player["level"] += 1
#         leveled_up = True

#     # Clamp current health/oxygen to new max after leveling
#     player["health"] = min(player["health"], get_max_health(player["level"]))
#     player["oxygen"] = min(player["oxygen"], get_max_oxygen(player["level"]))

#     players[uid] = player
#     save_players(players)
#     return player, leveled_up

# def make_progress_bar(current, total, length=20):
#     """Return a text progress bar."""
#     filled = int(length * current // total) if total > 0 else 0
#     empty = length - filled
#     return "█" * filled + "─" * empty

# def get_player_level(player_id):
#     players = load_json("players.json")["players"]
#     return players.get(str(player_id), {}).get("level", 1)


# ## ==================================================
# # ---------- PAGINATION HELPERS ----------
# ## ==================================================
# class CraftMenu(View):
#     def __init__(self, categories, player):
#         super().__init__(timeout=120)
#         self.categories = categories
#         self.player = player
#         self.index = 0
#         self.max_index = len(categories) - 1
#         self.update_buttons()

#     def update_buttons(self):
#         self.clear_items()
#         if self.index > 0:
#             self.add_item(self.PrevButton(self))
#         if self.index < self.max_index:
#             self.add_item(self.NextButton(self))

#     # ---------- BUTTON CALLBACKS ----------
#     class PrevButton(Button):
#         def __init__(self, menu):
#             super().__init__(label="⬅️ Prev", style=discord.ButtonStyle.primary)
#             self.menu = menu

#         async def callback(self, interaction: discord.Interaction):
#             self.menu.index = max(0, self.menu.index - 1)
#             self.menu.update_buttons()
#             await interaction.response.edit_message(embed=self.menu.make_embed(), view=self.menu)

#     class NextButton(Button):
#         def __init__(self, menu):
#             super().__init__(label="Next ➡️", style=discord.ButtonStyle.primary)
#             self.menu = menu

#         async def callback(self, interaction: discord.Interaction):
#             self.menu.index = min(self.menu.max_index, self.menu.index + 1)
#             self.menu.update_buttons()
#             await interaction.response.edit_message(embed=self.menu.make_embed(), view=self.menu)

#     async def interaction_check(self, interaction: discord.Interaction):
#         # Only allow the player who invoked the menu to interact
#         return interaction.user.id == self.player["id"]

#     async def on_timeout(self):
#         for child in self.children:
#             child.disabled = True
#         # Optional: edit message to disable buttons when timeout
#         # await some_message.edit(view=self)

#     def make_embed(self):
#         cat_name, recipes = self.categories[self.index]
#         embed = discord.Embed(title=f"Crafting Menu — {cat_name}", color=discord.Color.blue())
#         for recipe in recipes:
#             aliases = ", ".join(recipe.get("aliases", []))
#             desc = recipe.get("description", "No description.")
#             embed.add_field(
#                 name=f"{recipe.get('name', 'Unnamed')} (Aliases: {aliases})",
#                 value=desc,
#                 inline=False
#             )
#         return embed
    
# ## ===================================================
# ## ===== OXYGEN CONSUMPTION DECORATOR =====
# ## ===================================================
# def requires_oxygen(amount):
#     def decorator(func):
#         @wraps(func)
#         async def wrapper(ctx, *args, **kwargs):
#             # Fallback in case ctx.profiles wasn’t set yet
#             profiles = getattr(ctx, "profiles", None)
#             if not profiles:
#                 profiles = load_json(PLAYERS_FILE)
#                 ctx.profiles = profiles
#                 ctx.player = profiles.get(str(ctx.author.id), default_profile(ctx.author))

#             player = ctx.player
#             if player["oxygen"] < amount:
#                 await ctx.send(f"{ctx.author.mention}, you don’t have enough oxygen!")
#                 return

#             # Deduct oxygen
#             player["oxygen"] = max(0, player["oxygen"] - amount)

#             # Save
#             save_json(PLAYERS_FILE, ctx.profiles)

#             return await func(ctx, *args, **kwargs)
#         return wrapper
#     return decorator

# ##====================================================
# # ITEMS AND SHOP HELPERS (flexible for flat or category-grouped JSON)
# ##===================================================
# def iterate_all_items(items_data):
#     """Yield (item_id, item_dict) for both flat and category-grouped items.json structures."""
#     if not isinstance(items_data, dict):
#         return
#     # Detect flat (top-level keys are item ids with 'name')
#     if all(isinstance(v, dict) and "name" in v for v in items_data.values()):
#         for iid, itm in items_data.items():
#             yield iid, itm
#         return

#     # Otherwise assume categories at top level
#     for cat, group in items_data.items():
#         if isinstance(group, dict):
#             for iid, itm in group.items():
#                 yield iid, itm


# def get_item_by_id(items_data, item_id):
#     """
#     Look for an item in items_data (nested by category) by ID.
#     Returns the item dict or None if not found.
#     """
#     item_id = str(item_id)
#     for category in items_data.values():  # consumables, weapons, armor, etc.
#         if item_id in category:
#             return category[item_id]
#     return None


# def find_item(items, item_id):
#     """Find an item by ID across all categories."""
#     item_id = str(item_id)
#     for category in items.values():  # consumables, weapons, armor
#         if item_id in category:
#             return category[item_id]
#     return None


# # Crafting function
# async def craft_item(player, item_id, amount=1):
#     """
#     Craft a given item for the player.
#     player: dict (must contain 'inventory')
#     item_id: string (id or key of item to craft)
#     amount: int (number of items to craft)
#     Returns: (success: bool, message: str)
#     """
#     crafting_data = load_json(CRAFTING_FILE)
#     recipes = crafting_data.get("recipes", {})

#     if item_id not in recipes:
#         return False, f"Unknown recipe: {item_id}"

#     recipe = recipes[item_id]
#     materials_needed = recipe["materials"]
#     amount = max(1, amount)

#     missing_materials = []
#     # Check player inventory for required materials
#     for mat_id, qty_needed in materials_needed.items():
#         total_needed = qty_needed * amount
#         owned = player.get("inventory", {}).get(mat_id, 0)
#         if owned < total_needed:
#             missing_materials.append((mat_id, total_needed - owned))

#     if missing_materials:
#         missing_text = ", ".join(f"{mat} x{qty}" for mat, qty in missing_materials)
#         return False, f"You cannot craft {amount}x {item_id}. Missing: {missing_text}."

#     # Deduct materials
#     for mat_id, qty_needed in materials_needed.items():
#         total_needed = qty_needed * amount
#         player["inventory"][mat_id] -= total_needed
#         if player["inventory"][mat_id] <= 0:
#             del player["inventory"][mat_id]

#     # Add crafted items
#     player["inventory"][item_id] = player.get("inventory", {}).get(item_id, 0) + amount

#     return True, f"Crafted {amount}x {item_id}!"


# ## ===================================================
# #  ===== COOLDOWNS =====
# ## ===================================================

# # -------------------
# # Cooldown dictionary
# # -------------------
# command_cooldowns = {
#     "scan": 60,           # 1 minute
#     "work": 180,          # 3 minutes
#     "research": 600,      # 10 minutes
#     "explore": 3600,      # 1 hour
#     "bossfight": 43200,   # 12 hours
#     "daily": 86400,       # 24 hours
#     "weekly": 604800,     # 7 days
#     "lootbox": 10800      # 3 hours
# }

# # Load cooldowns from file
# if os.path.exists(COOLDOWNS_FILE):
#     with open(COOLDOWNS_FILE, "r") as f:
#         active_cooldowns = json.load(f)
# else:
#     active_cooldowns = {}

# # Save cooldowns to file
# def save_cooldowns():
#     with open(COOLDOWNS_FILE, "w", encoding="utf-8") as f:
#         json.dump(active_cooldowns, f, indent=4)

# # Set a cooldown for a user and command
# def set_cooldown(user_id, command, expires_at, username=None):
#     uid = str(user_id)
#     if uid not in active_cooldowns:
#         active_cooldowns[uid] = {"username": username or f"user_{uid}", "cooldowns": {}}
#     if "cooldowns" not in active_cooldowns[uid]:
#         active_cooldowns[uid]["cooldowns"] = {}
#     active_cooldowns[uid]["username"] = username or f"user_{uid}"  # Update username if provided
#     active_cooldowns[uid]["cooldowns"][command] = expires_at
#     save_cooldowns()

# # Get the remaining cooldown time for a user and command
# def get_cooldown(user_id, command):
#     uid = str(user_id)
#     user_data = active_cooldowns.get(uid, {})
#     cooldowns = user_data.get("cooldowns", {})
#     return cooldowns.get(command, 0)

# async def check_and_set_cooldown(ctx, command, cooldown_duration):
#     """Check if a command is on cooldown and set a new cooldown if not."""
#     user_id = str(ctx.author.id)
#     username = ctx.author.name  # Get the username from the context
#     now = int(time.time())

#     # Check cooldown
#     cooldown_expires = get_cooldown(user_id, command)
#     if now < cooldown_expires:
#         remaining = cooldown_expires - now
#         await ctx.send(f"⏳ You must wait {remaining} seconds before using `{command}` again.")
#         return False

#     # Set new cooldown
#     set_cooldown(user_id, command, now + cooldown_duration, username)
#     return True

# # Cleanup cooldowns (manual call)
# def cleanup_cooldowns():
#     now = int(time.time())
#     for user_id in list(active_cooldowns.keys()):
#         user_data = active_cooldowns[user_id]
#         cooldowns = user_data.get("cooldowns", {})
#         for command in list(cooldowns.keys()):
#             if cooldowns[command] < now:
#                 del cooldowns[command]
#         if not cooldowns:
#             del active_cooldowns[user_id]
#     save_cooldowns()

# # ===== standard reward message function =====
# def award_rewards(ctx, Scrap=0, xp=0):
#     """Award Scrap and XP to the player, handling level-ups and clamping health/oxygen."""
#     player = ctx.player
#     leveled_up = False

#     # Award Scrap
#     if Scrap > 0:
#         player["Scrap"] += Scrap

#     # Award XP
#     if xp > 0:
#         player["xp"] += xp
#         player["total_xp"] = player.get("total_xp", 0) + xp

#         # Level-up loop
#         while player["xp"] >= player["level"] * 100:
#             player["xp"] -= player["level"] * 100
#             player["level"] += 1
#             leveled_up = True

#     # Clamp health/oxygen after rewards
#     player["health"] = min(player["health"], get_max_health(player["level"]))
#     player["oxygen"] = min(player["oxygen"], get_max_oxygen(player["level"]))

#     # Build rewards message
#     parts = []
#     if Scrap > 0:
#         parts.append(f"💰 {Scrap} Scrap")
#     if xp > 0:
#         parts.append(f"⭐ {xp} XP")

#     msg = f"{ctx.author.mention} earned " + " + ".join(parts) + "!"
#     if leveled_up:
#         msg += f" 🎉 Level up! Now Level {player['level']}."

#     return msg

# # ====================================================
# # PLANET RESTRICTION DECORATOR
# # ===================================================
# def requires_planet(min_planet: int):
#     """Decorator to lock commands until the player reaches a minimum planet."""
#     def decorator(func):
#         @wraps(func)
#         async def wrapper(ctx, *args, **kwargs):
#             player = getattr(ctx, "player", None)
#             if not player:
#                 await ctx.send("⚠️ No player profile found.")
#                 return

#             current_planet = player.get("current_planet", 1)
#             if current_planet < min_planet:
#                 await ctx.send(
#                     f"🚫 You must reach Planet {min_planet} before using this command! "
#                     f"(You are currently on Planet {current_planet}.)"
#                 )
#                 return

#             return await func(ctx, *args, **kwargs)
#         return wrapper
#     return decorator

# # ====================================================
# # OXYGEN REGENERATION FUNCTION
# # ====================================================

# def apply_oxygen_regen(player):
#     """Apply passive oxygen regeneration based on armor and active Oxygen Tank."""
#     now = int(time.time())
#     last_regen = player.get("last_regen", now)
#     elapsed = now - last_regen

#     if elapsed < 60:
#         return player  # not enough time has passed

#     # How many minutes passed
#     minutes = elapsed // 60
#     player["last_regen"] = last_regen + minutes * 60

#     equipped = player.get("equipped", {})
#     armor_id = equipped.get("armor")
#     items = load_json(ITEMS_FILE)

#     if not armor_id:
#         return player  # no armor
#     armor = get_item_by_id(items, armor_id)
#     if not armor:
#         return player

#     regen_per_minute = armor.get("oxygen_regen", 0)
#     efficiency = armor.get("oxygen_efficiency", 1.0)
#     if regen_per_minute <= 0:
#         return player

#     # Ensure active_tank is valid
#     active_tank = player.get("active_tank")
#     if not active_tank or active_tank.get("remaining", 0) <= 0:
#         # Try to load a fresh Oxygen Tank from inventory
#         oxygen_tank_id = "1"
#         inventory = player.get("inventory", {})
#         if inventory.get(oxygen_tank_id, 0) > 0:
#             tank_item = get_item_by_id(items, oxygen_tank_id)
#             if not tank_item:
#                 return player  # item not defined
#             player["active_tank"] = {
#                 "id": oxygen_tank_id,
#                 "remaining": tank_item.get("value", 50)
#             }
#             inventory[oxygen_tank_id] -= 1
#             player["inventory"] = inventory
#         else:
#             return player  # no tanks available
#         active_tank = player["active_tank"]

#     # Oxygen regen process
#     total_regen = regen_per_minute * minutes
#     max_oxygen = get_max_oxygen(player.get("level", 1))
#     current_oxygen = player.get("oxygen", 0)

#     for _ in range(total_regen):
#         if current_oxygen >= max_oxygen:
#             break
#         if active_tank["remaining"] <= 0:
#             # Tank is empty -> clear it so a new one is loaded next tick
#             player["active_tank"] = None
#             break
#         # Apply regen tick
#         current_oxygen += 1
#         active_tank["remaining"] -= 1 / efficiency

#     player["oxygen"] = min(current_oxygen, max_oxygen)
#     return player



# # ====================================================
# # BOT COMMANDS
# # ====================================================

# # ====== GROUP CONFIG ======
# COMMAND_GROUPS = {
#     "Play": ["scan", "work", "research", "explore"],
#     "Inventory": ["inventory", "equip", "craft", "use", "open"],
#     "Misc": ["commands", "ready", "daily", "lootbox", "profile", "help"]
# }

# WORK_COMMANDS = ["scavenge", "hack", "extract", "harvest"]

# GROUP_EMOJIS = {
#     "Play": "🚀",
#     "Inventory": "🎒",
#     "Misc": "⚙️"
# }

# # Commands with cooldowns
# COOLDOWN_COMMANDS = {"scan", "work", "research", "explore", "daily", "lootbox"}


# # ====== COMMANDS LIST COMMAND ======
# @bot.command(name="commands", aliases=["cmds", "cmd"])
# @with_profile()
# async def commands_list(ctx):
#     """Show all commands grouped, with cooldowns for applicable commands in a sci-fi terminal style."""
#     user_id = str(ctx.author.id)
#     now = int(time.time())

#     lines = ["**💻 Command Interface — Available Commands:**"]

#     for group_name, cmd_list in COMMAND_GROUPS.items():
#         emoji = GROUP_EMOJIS.get(group_name, "🛠️")
#         lines.append(f"\n{emoji} __**{group_name} Commands:**__")

#         for cmd_name in cmd_list:
#             # Special handling for work (shared cooldown)
#             if cmd_name == "work":
#                 cooldown_expires = get_cooldown(user_id, "work")
#                 work_display = ", ".join(f"`{c}`" for c in WORK_COMMANDS)
#                 if now < cooldown_expires:
#                     remaining = cooldown_expires - now
#                     td = str(timedelta(seconds=math.ceil(remaining)))
#                     lines.append(f"   🕒 {work_display} — shared cooldown: {td}")
#                 else:
#                     lines.append(f"   ✅ {work_display} — ready!")
#                 continue

#             cmd = bot.get_command(cmd_name)

#             # If command isn't registered, mark it
#             if not cmd:
#                 lines.append(f"   ❌ `{cmd_name}` — not registered")
#                 continue

#             # Handle cooldown commands
#             if cmd_name in COOLDOWN_COMMANDS:
#                 cooldown_expires = get_cooldown(user_id, cmd_name)
#                 if now < cooldown_expires:
#                     remaining = cooldown_expires - now
#                     td = str(timedelta(seconds=math.ceil(remaining)))
#                     lines.append(f"   🕒 `{cmd_name}` — cooldown: {td}")
#                 else:
#                     lines.append(f"   ✅ `{cmd_name}` — ready!")
#             else:
#                 # Always-available commands
#                 lines.append(f"   ⚙️ `{cmd_name}` — always available")

#     await ctx.send("\n".join(lines))


# # ====== READY COMMAND ======
# @bot.command(name="ready", aliases=["rd"])
# @with_profile()
# async def ready(ctx):
#     """Show only cooldown commands that are ready to use."""
#     user_id = str(ctx.author.id)
#     now = int(time.time())

#     ready_lines = ["**✅ Commands Ready — Immediate Use:**"]

#     for cmd_name in COOLDOWN_COMMANDS:
#         # Work command shared handling
#         if cmd_name == "work":
#             cooldown_expires = get_cooldown(user_id, "work")
#             if now >= cooldown_expires:
#                 work_display = ", ".join(f"`{c}`" for c in WORK_COMMANDS)
#                 ready_lines.append(f"   🚀 {work_display}")
#             continue

#         cmd = bot.get_command(cmd_name)
#         if not cmd:
#             ready_lines.append(f"   ❌ `{cmd_name}` — not registered")
#             continue

#         cooldown_expires = get_cooldown(user_id, cmd_name)
#         if now >= cooldown_expires:
#             ready_lines.append(f"   🚀 `{cmd_name}`")

#     if len(ready_lines) == 1:
#         ready_lines.append("   _No commands ready yet._")

#     await ctx.send("\n".join(ready_lines))


# # ====== PROFILE COMMAND ======
# @bot.command(name="profile", aliases=["me", "stats", "p", "pro"])
# @with_profile()
# async def profile(ctx):
#     """Show your profile stats with XP progress bar + total XP + planet info."""
#     player = ctx.player
#     current_xp = player.get("xp", 0)
#     next_level_xp = player.get("level", 1) * 100
#     bar = make_progress_bar(current_xp, next_level_xp)

#     equipped = player.get("equipped", {})

#     # Load items and planets JSON
#     items = load_json(ITEMS_FILE)
#     planets = load_json(PLANETS_FILE)

#     # Fetch equipped item details
#     weapon = get_item_by_id(items, equipped.get("weapon"))
#     armor = get_item_by_id(items, equipped.get("armor"))

#     # ✅ Dynamic combat stats
#     stats = calculate_combat_stats(player)

#     # Planet info
#     current_planet = player.get("current_planet", 1)
#     max_planet = player.get("max_unlocked_planet", 1)
#     planet_name = planets.get(str(current_planet), {}).get("name", f"Planet {current_planet}")

#     embed = discord.Embed(
#         title=f"{player['username']}'s Profile",
#         color=discord.Color.blue()
#     )
#     embed.add_field(name="Level", value=str(player.get("level", 1)), inline=True)
#     embed.add_field(name="Total XP", value=str(player.get("total_xp", 0)), inline=True)
#     embed.add_field(name="Scrap", value=str(player.get("Scrap", 0)), inline=True)

#     embed.add_field(
#         name="XP Progress",
#         value=f"{current_xp}/{next_level_xp} {bar}",
#         inline=False
#     )

#     embed.add_field(
#         name="Health",
#         value=f"{player.get('health', 0)}/{get_max_health(player)} 🫀",
#         inline=True
#     )
#     embed.add_field(
#         name="Oxygen",
#         value=f"{player.get('oxygen', 0)}/{get_max_oxygen(player)} 🫁",
#         inline=True
#     )

#     embed.add_field(
#         name="Combat Stats",
#         value=f"Attack: {stats['attack']} ⚔️\nDefense: {stats['defense']} 🛡️",
#         inline=False
#     )

#     embed.add_field(
#         name="Equipped",
#         value=f"Weapon: {weapon['name'] if weapon else 'None'}\nArmor: {armor['name'] if armor else 'None'}",
#         inline=False
#     )

#     # Planet info field
#     embed.add_field(
#         name="Travel",
#         value=f"🌍 Current: **{planet_name}** (ID: {current_planet})\n"
#               f"🚀 Max Unlocked: Planet {max_planet}",
#         inline=False
#     )

#     embed.set_footer(text=f"ID: {ctx.author.id}")
#     embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else discord.Embed.Empty)

#     await ctx.send(embed=embed)
    

# ## ======= INVENTORY COMMAND =======
# @bot.command(aliases=["inv", "i"])
# @with_profile()
# async def inventory(ctx):
#     """View your categorized inventory."""
#     player = ctx.player
#     inventory = player.get("inventory", {})

#     if not inventory:
#         await ctx.send(f"{ctx.author.mention}, your inventory is empty!")
#         return

#     items = load_json(ITEMS_FILE)

#     # Prepare categories
#     categories = {
#         "Gear ⚙️": [],
#         "Drops 💧": [],
#         "Consumables 🍖": [],
#         "Materials 🪨": [],
#         "Lootboxes 🎁": [],
#         "Warpdrives 🚀": [],
#         "Unknown ❓": []
#     }

#     # Loop through inventory items
#     for item_id, quantity in inventory.items():
#         found = False
#         for cat_name, cat_items in items.items():  # items.json categories
#             if item_id in cat_items:
#                 item = cat_items[item_id]
#                 item_type = item.get("type", "").lower()

#                 # Sort by item type keywords
#                 if item_type in ["weapon", "armor", "gear"]:
#                     categories["Gear ⚙️"].append(f"**{item['name']}** x{quantity}")
#                 elif item_type in ["drop", "enemy_drop"]:
#                     categories["Drops 💧"].append(f"**{item['name']}** x{quantity}")
#                 elif item_type in ["consumable", "potion", "food"]:
#                     categories["Consumables 🍖"].append(f"**{item['name']}** x{quantity}")
#                 elif item_type in ["material", "resource"]:
#                     categories["Materials 🪨"].append(f"**{item['name']}** x{quantity}")
#                 elif item_type in ["lootbox", "crate"]:
#                     categories["Lootboxes 🎁"].append(f"**{item['name']}** x{quantity}")
#                 elif item_type in ["warpdrive", "key_item"]:
#                     categories["Warpdrives 🚀"].append(f"**{item['name']}** x{quantity}")
#                 else:
#                     categories["Unknown ❓"].append(f"**{item['name']}** x{quantity}")
#                 found = True
#                 break

#         if not found:
#             categories["Unknown ❓"].append(f"Unknown Item ({item_id}) x{quantity}")

#     # Build embed
#     embed = discord.Embed(
#         title=f"{ctx.author.name}'s Inventory",
#         color=discord.Color.gold()
#     )

#     # Only include categories with items
#     for title, items_list in categories.items():
#         if items_list:
#             embed.add_field(name=title, value="\n".join(items_list), inline=False)

#     embed.set_footer(text=f"Total unique items: {len(inventory)}")
#     embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else discord.Embed.Empty)

#     await ctx.send(embed=embed)


# ## ====== USE ITEM COMMAND ======
# @bot.command()
# @with_profile()
# async def use(ctx, *, item_query: str):
#     """Use an item from your inventory (by name or alias)."""
#     player = ctx.player
#     inventory = player.get("inventory", {})
#     items = load_json(ITEMS_FILE)

#     item_query = item_query.lower().strip()

#     # Search inventory by name/alias
#     target_item_id = None
#     target_item = None
#     for inv_id, quantity in inventory.items():
#         if quantity <= 0:
#             continue

#         item = find_item(items, inv_id)
#         if not item:
#             continue

#         names = [item["name"].lower()] + [a.lower() for a in item.get("aliases", [])]
#         if item_query in names:
#             target_item_id = str(inv_id)
#             target_item = item
#             break

#     if not target_item:
#         await ctx.send(f"{ctx.author.mention}, you don’t have `{item_query}` in your inventory!")
#         return

#     # Apply effects
#     if target_item["effect"] == "restore_oxygen":
#         old = player["oxygen"]
#         player["oxygen"] = min(player["oxygen"] + target_item["value"], get_max_oxygen(player["level"]))
#         gained = player["oxygen"] - old
#         await ctx.send(f"{ctx.author.mention} used **{target_item['name']}** and restored {gained} oxygen! 🫁 You now have {player.get('oxygen')}/{get_max_oxygen(player['level'])}")

#     elif target_item["effect"] == "restore_health":
#         old = player["health"]
#         player["health"] = min(player["health"] + target_item["value"], get_max_health(player["level"]))
#         gained = player["health"] - old
#         await ctx.send(f"{ctx.author.mention} used **{target_item['name']}** and restored {gained} health! :anatomical_heart: You now have {player.get('health')}/{get_max_health(player['level'])}")

#     else:
#         await ctx.send(f"{ctx.author.mention}, **{target_item['name']}** had no effect!")

#     # Remove one from inventory
#     inventory[target_item_id] -= 1
#     if inventory[target_item_id] <= 0:
#         del inventory[target_item_id]
#     player["inventory"] = inventory
    

# # ====== SHOP COMMAND ======
# @bot.command()
# @with_profile()
# async def shop(ctx):
#     """View items available in the shop, shown in an embed grouped by category with buy examples."""
#     player = ctx.player
#     shop_data = load_json(SHOP_FILE)
#     items_data = load_json(ITEMS_FILE)

#     Scrap = player.get("Scrap", 0)

#     embed = discord.Embed(
#         title="🛒 Galactic Shop",
#         description=f"Your Scrap: 💳 {Scrap}\nBrowse and purchase items using `!buy <name/alias>`.",
#         color=discord.Color.blue()
#     )

#     # Loop categories
#     for category, items in shop_data.items():
#         lines = []
#         for item_id, shop_entry in items.items():
#             item = get_item_by_id(items_data, item_id)
#             if not item:
#                 name = f"Unknown Item ({item_id})"
#                 description = shop_entry.get("description", "No description.")
#                 aliases = []
#             else:
#                 name = item.get("name", f"Unknown Item ({item_id})")
#                 description = shop_entry.get("description") or item.get("description", "No description.")
#                 aliases = item.get("aliases", [])

#             price = shop_entry.get("price", "N/A")

#             # Show aliases as buy examples
#             alias_str = ""
#             if aliases:
#                 alias_examples = [f"`!buy {a}`" for a in aliases[:3]]  # limit to first 3 to avoid clutter
#                 alias_str = f"\n*Try: {' / '.join(alias_examples)}*"

#             lines.append(f"**{name}** — 💳 {price}\n{description}{alias_str}")

#         if lines:
#             embed.add_field(
#                 name=category.capitalize(),
#                 value="\n\n".join(lines),
#                 inline=False
#             )

#     if not embed.fields:
#         await ctx.send("The shop is currently empty.")
#         return

#     await ctx.send(embed=embed)


# # ====== BUY COMMAND ======
# @bot.command(name="buy")
# @with_profile()
# async def buy(ctx, item_name: str, amount: int = 1):
#     """
#     Buy items by name, alias, or ID. Amount defaults to 1 (clamped 1..100).
#     Example: !buy oxy 2
#     Lootboxes use the global cooldown system (3 hours).
#     """
#     player = ctx.player
#     shop_data = load_json(SHOP_FILE)
#     items_data = load_json(ITEMS_FILE)

#     query = item_name.lower().strip()
#     amount = max(1, min(amount, 100))

#     # Search across all categories
#     target_item_id = None
#     target_shop_entry = None
#     target_item_obj = None

#     for category, entries in shop_data.items():
#         for item_id, shop_entry in entries.items():
#             item_obj = get_item_by_id(items_data, item_id)
#             if not item_obj:
#                 continue
#             names = [str(item_id).lower(), item_obj.get("name", "").lower()] + [
#                 a.lower() for a in item_obj.get("aliases", [])
#             ]
#             if query in names:
#                 target_item_id = str(item_id)
#                 target_shop_entry = shop_entry
#                 target_item_obj = item_obj
#                 break
#         if target_item_id:
#             break

#     if not target_item_id:
#         await ctx.send(f"{ctx.author.mention} That item doesn’t exist in the shop.")
#         return

#     # ===== SPECIAL HANDLING FOR KEYCARD =====
#     if target_item_obj["type"] == "key" and "keycard" in target_item_obj["name"].lower():
#         planet_id = player.get("max_unlocked_planet", 1)
#         base_cost = 500  # tweak as needed
#         price_each = base_cost * (planet_id ** 2)  # quadratic scaling
#         total_price = price_each * amount

#     # ===== SPECIAL HANDLING FOR LOOTBOX =====
#     elif target_item_obj["type"] == "lootbox":
#         cooldown_duration = command_cooldowns.get("lootbox", 10800)  # 3 hours default
#         can_buy = await check_and_set_cooldown(ctx, "lootbox", cooldown_duration)
#         if not can_buy:
#             return  # message already sent by check_and_set_cooldown()

#         price_each = target_shop_entry.get("price", 0)
#         total_price = price_each * amount

#     # ===== DEFAULT COST =====
#     else:
#         price_each = target_shop_entry.get("price", 0)
#         total_price = price_each * amount

#     # Check Scrap
#     if player.get("Scrap", 0) < total_price:
#         await ctx.send(
#             f"{ctx.author.mention} You don’t have enough Scrap for {amount}x **{target_item_obj['name']}** (💳 {total_price})."
#         )
#         return

#     # Deduct Scrap and add to inventory
#     player["Scrap"] = player.get("Scrap", 0) - total_price
#     inventory = player.get("inventory", {})
#     inventory[target_item_id] = inventory.get(target_item_id, 0) + amount
#     player["inventory"] = inventory

#     save_profile(ctx.author.id, player)

#     await ctx.send(
#         f"{ctx.author.mention} bought **{amount}x {target_item_obj['name']}** for 💳 {total_price} Scrap!"
#     )


# # ====== EQUIP COMMAND ======
# @bot.command()
# @with_profile()
# async def equip(ctx, *, item_name: str):
#     """Equip a weapon or armor from your inventory by name or alias."""
#     player = ctx.player
#     inventory = player.get("inventory", {})
#     items = load_json(ITEMS_FILE)
#     item_name = item_name.lower()

#     # Search player inventory for matching item
#     target_id = None
#     target_item = None
#     for category, item_dict in items.items():
#         for item_id, item in item_dict.items():
#             if str(item_id) not in inventory or inventory[str(item_id)] <= 0:
#                 continue
#             names = [item["name"].lower()] + [a.lower() for a in item.get("aliases", [])]
#             if item_name in names:
#                 target_id = item_id
#                 target_item = item
#                 break
#         if target_item:
#             break  # stop after finding the first valid item

#     if not target_item:
#         await ctx.send(f"{ctx.author.mention}, you don’t have that item in your inventory!")
#         return

#     # Only weapons/armor can be equipped
#     if target_item["type"] not in ["weapon", "armor"]:
#         await ctx.send(f"{ctx.author.mention}, you can’t equip {target_item['name']}!")
#         return

#     # Equip item
#     player.setdefault("equipped", {})[target_item["type"]] = target_id
#     save_profile(player["id"], player)  # ✅ save equipped changes

#     # Calculate effective stats dynamically
#     stats = calculate_combat_stats(player)

#     await ctx.send(
#         f"{ctx.author.mention} equipped **{target_item['name']}** "
#         f"→ Attack: {stats['attack']} ⚔️ | Defense: {stats['defense']} 🛡️"
#     )

# # ====== CRAFT COMMAND ======
# @bot.command(name="craft", aliases=["make", "cr"])
# @with_profile()
# async def craft(ctx, *, item_and_amount: str = None):
#     """
#     Craft items using the crafting.json recipes.
#     Usage:
#       !craft <item_name>
#       !craft <item_name> <amount>
#       !craft <item_name> all

#     Examples:
#       !craft Plasteel Sheet
#       !craft Plasteel Sheet 2
#       !craft sheet all
#     """
#     player = ctx.player
#     crafting_data = load_json(CRAFTING_FILE).get("recipes", {})
#     items_data = load_json(ITEMS_FILE)

#     if not item_and_amount:
#         await ctx.send(f"{ctx.author.mention} ❌ You must specify an item to craft. Example: `!craft Plasteel Sheet 2`.")
#         return

#     # --- Split into item name + amount ---
#     parts = item_and_amount.rsplit(" ", 1)
#     if len(parts) == 2 and parts[1].isdigit():
#         item_name, amount = parts[0], int(parts[1])
#     elif len(parts) == 2 and parts[1].lower() == "all":
#         item_name, amount = parts[0], "all"
#     else:
#         item_name, amount = item_and_amount, 1

#     item_name = item_name.lower().strip()

#     # --- Find recipe by key, name, or alias ---
#     recipe_key, recipe = None, None
#     for key, r in crafting_data.items():
#         names = [key.lower()]
#         if "name" in r:
#             names.append(r["name"].lower())
#         names.extend([a.lower() for a in r.get("aliases", [])])
#         if item_name in names:
#             recipe_key, recipe = key, r
#             break

#     if not recipe:
#         await ctx.send(f"{ctx.author.mention} ❌ Unknown recipe: `{item_name}`")
#         return

#     # --- Level check ---
#     player_level = player.get("level", 1)
#     level_req = recipe.get("level_req", 0)
#     if player_level < level_req:
#         await ctx.send(f"⚠️ You need to be **Level {level_req}** to craft {recipe.get('name', recipe_key)}. (Your level: {player_level})")
#         return

#     # --- Determine craft amount ---
#     if isinstance(amount, str) and amount.lower() == "all":
#         max_craft = float("inf")
#         for mat_id, qty_needed in recipe["materials"].items():
#             available = player.get("inventory", {}).get(mat_id, 0)
#             max_craft = min(max_craft, available // qty_needed)
#         amount_to_craft = int(max_craft) if max_craft > 0 else 0
#         if amount_to_craft == 0:
#             await ctx.send(f"{ctx.author.mention} ❌ You don’t have enough materials to craft any {recipe.get('name', recipe_key)}.")
#             return
#     else:
#         if isinstance(amount, int):
#             amount_to_craft = max(1, min(100, amount))
#         else:
#             await ctx.send(f"{ctx.author.mention} ❌ Invalid amount: {amount}")
#             return

#     # --- Check materials ---
#     inventory = player.get("inventory", {})
#     for mat_id, qty_needed in recipe["materials"].items():
#         if inventory.get(mat_id, 0) < qty_needed * amount_to_craft:
#             await ctx.send(f"{ctx.author.mention} ❌ Not enough `{mat_id}` to craft {amount_to_craft}x {recipe.get('name', recipe_key)}.")
#             return

#     # --- Deduct materials ---
#     for mat_id, qty_needed in recipe["materials"].items():
#         inventory[mat_id] -= qty_needed * amount_to_craft
#         if inventory[mat_id] <= 0:
#             inventory.pop(mat_id)

#     # --- Add crafted items ---
#     output_id = recipe_key  # either an item id (e.g. "101") or material key
#     output_qty = recipe.get("output", 1) * amount_to_craft
#     inventory[output_id] = inventory.get(output_id, 0) + output_qty
#     player["inventory"] = inventory

#     await ctx.send(f"{ctx.author.mention} ✅ Crafted **{amount_to_craft}x {recipe.get('name', recipe_key)}**!")


# # ====== RECIPES COMMAND ======

# ITEMS_PER_PAGE = 5 # Number of recipes per page

# class RecipesView(View):
#     def __init__(self, recipes, category, ctx):
#         super().__init__(timeout=60)
#         self.recipes = recipes
#         self.category = category
#         self.ctx = ctx
#         self.index = 0

#         # Buttons
#         self.prev_button = Button(label="⬅️ Previous", style=discord.ButtonStyle.primary)
#         self.next_button = Button(label="➡️ Next", style=discord.ButtonStyle.primary)
#         self.add_item(self.prev_button)
#         self.add_item(self.next_button)

#         # Bind callbacks
#         self.prev_button.callback = self.prev_page
#         self.next_button.callback = self.next_page

#     def make_embed(self):
#         embed = discord.Embed(
#             title=f"📜 Recipes: {self.category.title()} (Page {self.index+1}/{self.total_pages})",
#             color=discord.Color.green()
#         )
#         start = self.index * ITEMS_PER_PAGE
#         end = start + ITEMS_PER_PAGE
#         page_recipes = self.recipes[start:end]

#         for r in page_recipes:
#             name = r.get("name", "Unknown")
#             description = r.get("description", "")
#             aliases = r.get("aliases", [])
#             aliases_str = ", ".join(aliases) if aliases else "None"
#             materials = r.get("materials", {})
#             materials_str = ", ".join([f"{k}: {v}" for k, v in materials.items()]) if materials else "None"
#             level_req = r.get("level_req", 0)


#             value = f"**Description:** {description}\n**Aliases:** {aliases_str}\n**Materials:** {materials_str}"
#             if len(value) > 1024:
#                 value = value[:1021] + "..."
#             if level_req > 0:
#                 value += f"\n**Level Requirement:** {level_req}"
#             embed.add_field(name=name, value=value, inline=False)

#         return embed

#     @property
#     def total_pages(self):
#         return (len(self.recipes) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

#     async def prev_page(self, interaction: discord.Interaction):
#         if interaction.user != self.ctx.author:
#             await interaction.response.send_message("You can’t control this menu.", ephemeral=True)
#             return
#         if self.index > 0:
#             self.index -= 1
#             await interaction.response.edit_message(embed=self.make_embed(), view=self)

#     async def next_page(self, interaction: discord.Interaction):
#         if interaction.user != self.ctx.author:
#             await interaction.response.send_message("You can’t control this menu.", ephemeral=True)
#             return
#         if self.index < self.total_pages - 1:
#             self.index += 1
#             await interaction.response.edit_message(embed=self.make_embed(), view=self)


# @bot.command(name="recipes", aliases=["rcp", "recipe", "rec"])
# async def recipes(ctx, category: str = None):
#     """Show crafting categories or recipes in a category with pagination."""
#     crafting_data = load_json(CRAFTING_FILE)
#     recipes_dict = crafting_data.get("recipes", {})

#     if not category:
#         # Show available categories
#         categories = set(r.get("category", "Unknown") for r in recipes_dict.values())
#         embed = discord.Embed(title="🛠 Crafting Categories", color=discord.Color.blue())
#         embed.description = ", ".join(sorted(categories))
#         embed.add_field(name="Usage", value="Type `!recipes <category>` to view recipes in that category.")
#         await ctx.send(embed=embed)
#         return

#     # Normalize category for matching
#     category = category.lower()
#     filtered = [r for r in recipes_dict.values() if r.get("category", "").lower() == category]

#     if not filtered:
#         await ctx.send(f"No recipes found for category `{category}`.")
#         return

#     view = RecipesView(filtered, category, ctx)
#     await ctx.send(embed=view.make_embed(), view=view)

# # ====== OPEN LOOTBOX COMMAND ======
# @bot.command(name="open")
# @with_profile()
# async def open_lootbox(ctx, tier: str, amount: str = "1"):
#     """
#     Open lootboxes of a given tier and amount.
#     Examples:
#     !open c 10        -> opens 10 Common lootboxes
#     !open u all       -> opens all Uncommon lootboxes
#     !open r half      -> opens half of your Rare lootboxes
#     """

#     player = ctx.player
#     inventory = player.get("inventory", {})
#     items_data = load_json(ITEMS_FILE)

#     # Define lootbox mapping based on items.json
#     lootbox_map = {
#         "c": {"id": "300", "tier": "common", "name": "Common Lootbox"},
#         "u": {"id": "301", "tier": "uncommon", "name": "Uncommon Lootbox"},
#         "r": {"id": "302", "tier": "rare", "name": "Rare Lootbox"},
#         "m": {"id": "303", "tier": "mythic", "name": "Mythic Lootbox"},
#         "l": {"id": "304", "tier": "legendary", "name": "Legendary Lootbox"},
#     }

#     tier = tier.lower()
#     if tier not in lootbox_map:
#         await ctx.send(
#             f"{ctx.author.mention}, invalid lootbox type! "
#             "Use one of: c, u, r, m, l."
#         )
#         return

#     lootbox = lootbox_map[tier]
#     lootbox_id = lootbox["id"]
#     lootbox_name = lootbox["name"]
#     lootbox_tier = lootbox["tier"]

#     owned = inventory.get(lootbox_id, 0)
#     if owned <= 0:
#         await ctx.send(f"{ctx.author.mention}, you don’t have any {lootbox_name}s to open!")
#         return

#     # Parse how many boxes to open
#     if amount.lower() == "all":
#         open_count = owned
#     elif amount.lower() == "half":
#         open_count = max(1, owned // 2)
#     else:
#         try:
#             open_count = max(1, min(int(amount), owned))
#         except ValueError:
#             await ctx.send("Invalid amount! Use a number, 'all', or 'half'.")
#             return

#     # Remove opened boxes from inventory
#     inventory[lootbox_id] = owned - open_count

#     # Generate rewards
#     all_rewards = {}
#     for _ in range(open_count):
#         rewards = generate_lootbox_contents(player, lootbox_tier, items_data)
#         for item_id, qty in rewards.items():
#             inventory[item_id] = inventory.get(item_id, 0) + qty
#             all_rewards[item_id] = all_rewards.get(item_id, 0) + qty

#     # Update player inventory
#     player["inventory"] = inventory

#     # Format rewards for message
#     reward_lines = []
#     for item_id, qty in sorted(all_rewards.items(), key=lambda x: -x[1]):
#         item = get_item_by_id(items_data, item_id)
#         item_name = item["name"] if item else item_id
#         emoji = item.get("emoji", "") if item else ""
#         reward_lines.append(f"{emoji} **{item_name}** x{qty}")

#     # Prepare embed
#     embed = discord.Embed(
#         title=f"🎁 {ctx.author.name} opened {open_count}x {lootbox_name}!",
#         description="\n".join(reward_lines) if reward_lines else "No items received.",
#         color=discord.Color.gold()
#     )
#     embed.set_footer(text=f"Lootbox tier: {lootbox_tier.title()}")

#     await ctx.send(embed=embed)

    
# # Helper function to generate lootbox contents
# def generate_lootbox_contents(player, tier, items_data):
#     """
#     Generate rewards for a given lootbox tier, considering:
#     - Tier rarity weighting
#     - Player progression (planet unlocks)
#     - Material & mob drop unlock rules
#     """

#     unlocked_planet = player.get("max_unlocked_planet", 1)
#     rewards = {}

#     # ========================
#     # 1️⃣ Tier weight settings
#     # ========================
#     tier_config = {
#         "common":    {"rolls": (2, 3), "mult": 1.0, "rarity_weight": {"common": 80, "uncommon": 20, "rare": 0, "mythic": 0, "legendary": 0}},
#         "uncommon":  {"rolls": (3, 4), "mult": 1.25, "rarity_weight": {"common": 50, "uncommon": 40, "rare": 10, "mythic": 0, "legendary": 0}},
#         "rare":      {"rolls": (4, 6), "mult": 1.5, "rarity_weight": {"common": 25, "uncommon": 45, "rare": 25, "mythic": 5, "legendary": 0}},
#         "mythic":    {"rolls": (6, 8), "mult": 1.75, "rarity_weight": {"common": 15, "uncommon": 35, "rare": 35, "mythic": 15, "legendary": 0}},
#         "legendary": {"rolls": (8, 10), "mult": 2.0, "rarity_weight": {"common": 5, "uncommon": 25, "rare": 40, "mythic": 20, "legendary": 10}},
#     }

#     cfg = tier_config.get(tier, tier_config["common"])
#     num_rolls = random.randint(*cfg["rolls"])

#     # ========================
#     # 2️⃣ Build loot pool
#     # ========================

#     materials = []
#     drops = []

#     # Material unlock logic (planet gating)
#     material_unlocks = [
#         ("plasteel", 1),
#         ("circuit", 1),
#         ("plasma", 3),
#         ("biofiber", 5)
#     ]

#     for name, planet_req in material_unlocks:
#         if unlocked_planet >= planet_req:
#             # Include all variants of that material (basic → block)
#             for tier_suffix in ["", "_sheet", "_bar", "_beam", "_block"]:
#                 full_id = name + tier_suffix
#                 if full_id in items_data.get("materials", {}):
#                     materials.append(full_id)

#     # Mob drops gating by planet
#     for drop_id, drop_data in items_data.get("drops", {}).items():
#         allowed_planets = drop_data.get("planet", [])
#         if any(p <= unlocked_planet for p in allowed_planets):
#             drops.append(drop_id)

#     # Base pool
#     loot_pool = materials + drops
#     if not loot_pool:
#         return {}  # No loot unlocked yet

#     # ========================
#     # 3️⃣ Roll rewards
#     # ========================
#     for _ in range(num_rolls):
#         item_id = random.choice(loot_pool)

#         # Determine rarity multiplier for quantity
#         rarity_roll = random.choices(
#             list(cfg["rarity_weight"].keys()),
#             weights=list(cfg["rarity_weight"].values())
#         )[0]

#         # Scale quantities by rarity and tier
#         base_qty = random.randint(1, 3)
#         rarity_mult = {
#             "common": 1.0,
#             "uncommon": 1.2,
#             "rare": 1.5,
#             "mythic": 2.0,
#             "legendary": 3.0,
#         }.get(rarity_roll, 1.0)

#         total_qty = max(1, int(base_qty * rarity_mult * cfg["mult"]))
#         rewards[item_id] = rewards.get(item_id, 0) + total_qty

#     return rewards


# ## =========================================
# # ========== PROGRESSION COMMANDS ==========
# ## =========================================

# # ====== PLANET COMMAND ======
# @bot.command(name="planet")
# @with_profile()
# async def planet(ctx):
#     """Show info about your current planet."""
#     player = ctx.player
#     planet_id = str(player.get("current_planet", 1))
#     planets_data = load_json(PLANETS_FILE)
#     planet = planets_data.get(planet_id)

#     if not planet:
#         await ctx.send("❌ Current planet data not found.")
#         return

#     reqs = ", ".join(planet.get("requirements_names", [])) or "None"
#     msg = (
#         f"🪐 **{planet['name']}** (Planet {planet_id})\n"
#         f"Boss: {planet['boss']}\n"
#         f"Requirements: {reqs}\n"
#         f"Scrap Multiplier: {planet.get('scrap_mult',1)}\n"
#         f"XP Multiplier: {planet.get('xp_mult',1)}\n"
#         f"Materials Multiplier: {planet.get('materials_mult',1)}"
#     )
#     await ctx.send(msg)

# # ====== TRAVEL COMMAND ======
# @bot.command(name="travel")
# @with_profile()
# async def travel(ctx, planet_id: int):
#     """Travel to an unlocked planet."""
#     player = ctx.player
#     max_unlocked = player.get("max_unlocked_planet", 1)

#     if planet_id > max_unlocked:
#         await ctx.send(f"❌ You haven’t unlocked Planet {planet_id} yet.")
#         return

#     player["current_planet"] = planet_id
#     planets_data = load_json(PLANETS_FILE)
#     planet_name = planets_data.get(str(planet_id), {}).get("name", f"Planet {planet_id}")
#     await ctx.send(f"🛸 You traveled to **{planet_name}**.")


# ## ==========================================
# ## ========== BOSSFIGHT COMMAND =============
# ## ==========================================
# @bot.command(name="bossfight", aliases=["bf"])
# @with_profile(auto_save=False)
# async def bossfight(ctx, *members: discord.Member):
#     player_ids = [str(ctx.author.id)] + [str(m.id) for m in members if m.id != ctx.author.id]
#     if len(player_ids) > 4:
#         return await ctx.send("❌ You can only bring up to 3 allies (4 total).")

#     # Load profiles
#     profiles = {pid: load_profile(pid) for pid in player_ids}
#     if any(p is None for p in profiles.values()):
#         return await ctx.send("❌ One or more players do not have profiles.")

#     # Get planet & boss
#     planet_id = profiles[player_ids[0]].get("current_planet", 1)
#     boss = load_boss_for_planet(planet_id, len(player_ids))

#     # Requirements
#     if not await check_requirements(ctx, profiles, boss):
#         return

#     # Confirmation
#     if not await confirm_participation(ctx, player_ids, boss["name"]):
#         return

#     # Calculate combat stats
#     for pid, profile in profiles.items():
#         stats = calculate_combat_stats(profile)
#         profile["attack"], profile["defense"] = stats["attack"], stats["defense"]

#     # Consume keycards (update profiles in place)
#     for pid in player_ids:
#         profiles[pid] = consume_keycard(profiles[pid])

#     # Run combat
#     victory = await run_combat(ctx, profiles, player_ids, boss)

#     # Outcome
#     if victory:
#         await ctx.send(f"🏆 {boss['name']} was defeated! The path forward is open.")
#         for pid in player_ids:
#             warp_id, warp_name = grant_boss_rewards(pid, planet_id, profiles[pid])
#             if warp_id:
#                 await ctx.send(f"🔓 {profiles[pid]['username']} unlocked Planet {planet_id+1} and got **{warp_name}**!")
#     else:
#         await ctx.send(f"☠️ All players were defeated by {boss['name']}...")
#         for pid in player_ids:
#             profiles[pid] = apply_defeat_penalty(pid, profiles[pid])

#     # Final save (persist all profile changes once)
#     for pid in player_ids:
#         save_profile(pid, profiles[pid])
#         print(f"[DEBUG] Final save after fight -> {pid}: {profiles[pid]}")


# ## Helper function to load and scale boss data
# def load_boss_for_planet(planet_id: int, num_players: int):
#     """Load boss data from bosses.json and scale HP for multiple players."""
#     bosses = load_json(BOSSES_FILE)
#     boss_id = "crawler_king" if planet_id == 1 else "crawler_queen"  # extend later
#     boss = bosses[boss_id].copy()

#     base_hp = boss["hp"]
#     boss["hp"] = base_hp + (num_players - 1) * int(base_hp * 0.75)
#     return boss

# ## Helper function to check requirements
# async def check_requirements(ctx, profiles: dict, boss: dict):
#     """Check weapon, armor, and keycard requirements."""
#     req_weapon = boss.get("required_weapon_id")
#     req_armor = boss.get("required_armor_id")
#     req_keycard = "400"

#     for pid, profile in profiles.items():
#         equipped = profile.get("equipped", {})
#         if int(equipped.get("weapon", 0)) < req_weapon or int(equipped.get("armor", 0)) < req_armor:
#             await ctx.send(
#                 f"❌ {profile['username']} does not meet requirements "
#                 f"(Weapon ≥ {req_weapon}, Armor ≥ {req_armor})."
#             )
#             return False

#         if profile.get("inventory", {}).get(req_keycard, 0) <= 0:
#             await ctx.send(f"❌ {profile['username']} is missing the required keycard.")
#             return False

#     return True

# ## Helper function to confirm participation
# async def confirm_participation(ctx, player_ids, boss_name):
#     """Ask all players to confirm with yes/no before the fight."""
#     mention_list = ", ".join([f"<@{pid}>" for pid in player_ids])
#     await ctx.send(f"⚔️ {mention_list}, are you ready to challenge **{boss_name}**? Type `yes` or `no`.")

#     ready_responses = {}
#     def check_ready(m):
#         return str(m.author.id) in player_ids and m.content.lower() in ["yes", "no"]

#     while len(ready_responses) < len(player_ids):
#         try:
#             msg = await bot.wait_for("message", check=check_ready, timeout=30)
#             ready_responses[str(msg.author.id)] = msg.content.lower()
#         except asyncio.TimeoutError:
#             await ctx.send("⌛ Bossfight cancelled due to timeout.")
#             return False

#     if not all(r == "yes" for r in ready_responses.values()):
#         await ctx.send("❌ Not all players confirmed. Bossfight cancelled.")
#         return False

#     return True


# ## Helper function to consume a keycard
# def consume_keycard(profile: dict, keycard_id="400"):
#     """Consume one keycard from a player's loaded profile."""
#     inv = profile.get("inventory", {})
#     inv[keycard_id] = inv.get(keycard_id, 0) - 1
#     if inv[keycard_id] <= 0:
#         inv.pop(keycard_id, None)
#     profile["inventory"] = inv
#     return profile


# ## Helper function to calculate combat stats
# async def run_combat(ctx, profiles: dict, player_ids: list, boss: dict) -> bool:
#     """
#     Main combat loop. Uses a local `combatants` dict so saved profiles are untouched
#     during combat. Returns True if boss defeated, False if players all die.
#     """
#     # Build combatants from profiles (do not mutate profiles yet)
#     combatants = {}
#     for pid in player_ids:
#         profile = profiles[pid]
#         stats = calculate_combat_stats(profile)
#         combatants[pid] = {
#             "profile_ref": profile,
#             "attack": stats["attack"],
#             "defense": stats["defense"],
#             "health": profile.get("health", get_max_health(profile.get("level", 1))),
#             "username": profile.get("username", f"user_{pid}"),
#             "defending": False,
#             "dodging": False,
#         }

#     # Boss local stats (work on copies)
#     boss_hp = int(boss.get("hp", 0))
#     boss_base_attack = boss.get("attack", 0)
#     boss_base_defense = boss.get("defense", 0)

#     # Apply boss scaling multipliers if present (attack/defense multipliers per extra player)
#     num_players = len(player_ids)
#     scaling = boss.get("scaling", {}) or {}
#     if num_players > 1 and scaling:
#         atk_mult = float(scaling.get("attack_mult_per_player", 1.0)) ** (num_players - 1)
#         def_mult = float(scaling.get("defense_mult_per_player", 1.0)) ** (num_players - 1)
#         boss_attack = max(1, int(boss_base_attack * atk_mult))
#         boss_defense = max(0, int(boss_base_defense * def_mult))
#     else:
#         boss_attack = int(boss_base_attack)
#         boss_defense = int(boss_base_defense)

#     # Precompute ability list (if none, fallback to single generic attack)
#     abilities = list(boss.get("abilities", {}).values()) or [{
#         "name": "Strike",
#         "hit_chance": 0.85,
#         "damage_mult": 1.0,
#         "defense_pen": 0.0
#     }]

#     turn = 0
#     alive_pids = [pid for pid in player_ids if combatants[pid]["health"] > 0]

#     await ctx.send(f"🔥 The fight against **{boss['name']}** begins! HP: {boss_hp}")

#     while boss_hp > 0 and alive_pids:
#         pid = alive_pids[turn % len(alive_pids)]
#         fighter = combatants[pid]

#         # Skip if somehow dead
#         if fighter["health"] <= 0:
#             turn += 1
#             alive_pids = [p for p in alive_pids if combatants[p]["health"] > 0]
#             continue

#         # Ask player for action
#         await ctx.send(f"🎮 <@{pid}>, choose: `attack`, `defend`, `dodge`, or `power`.")

#         def check_action(m):
#             return str(m.author.id) == pid and m.content.lower() in ["attack", "defend", "dodge", "power"]

#         try:
#             msg = await bot.wait_for("message", check=check_action, timeout=30)
#             action = msg.content.lower()
#         except asyncio.TimeoutError:
#             action = "attack"

#         # Resolve player action -> damage to boss
#         dmg_to_boss = 0
#         if action == "attack" and random.random() < 0.8:
#             dmg_to_boss = max(1, fighter["attack"] - boss_defense)
#         elif action == "defend" and random.random() < 0.5:
#             dmg_to_boss = max(1, (fighter["attack"] // 2) - boss_defense)
#             fighter["defending"] = True
#         elif action == "dodge" and random.random() < 0.3:
#             dmg_to_boss = max(1, (fighter["attack"] // 3) - boss_defense)
#             fighter["dodging"] = True
#         elif action == "power" and random.random() < 0.4:
#             dmg_to_boss = max(5, fighter["attack"] * 2 - boss_defense)

#         boss_hp -= dmg_to_boss
#         boss_hp = max(0, boss_hp)  # keep non-negative
#         if dmg_to_boss > 0:
#             await ctx.send(f"💥 {fighter['username']} dealt **{dmg_to_boss}** damage! (Boss HP: {boss_hp})")
#         else:
#             await ctx.send(f"❌ {fighter['username']}'s move missed!")

#         if boss_hp <= 0:
#             break

#         # Boss chooses ability and attacks the same player
#         # Weighted ability choice
#         if len(abilities) >= 3:
#             # Assume order: [basic, medium, strong]
#             ability = random.choices(
#                 population=abilities,
#                 weights=[60, 30, 10],
#                 k=1
#             )[0]
#         else:
#             # Fallback: equal weighting if fewer abilities
#             ability = random.choice(abilities)
#         hit_chance = float(ability.get("hit_chance", 0.8))
#         # reduce hit chance if player dodging
#         if fighter.get("dodging"):
#             hit_chance -= 0.4
#         hit_roll = random.random()

#         if hit_roll < hit_chance:
#             dmg_mult = float(ability.get("damage_mult", 1.0))
#             # effective defense after defense penetration
#             def_pen = float(ability.get("defense_pen", 0.0))
#             effective_def = int(fighter["defense"] * (1.0 - def_pen))
#             raw = int(boss_attack * dmg_mult) - effective_def
#             dmg_taken = max(1, raw)

#             # defending halves the incoming damage
#             if fighter.get("defending"):
#                 dmg_taken = dmg_taken // 2

#             fighter["health"] -= dmg_taken
#             await ctx.send(
#                 f"⚡ {boss['name']} used **{ability.get('name','attack')}** and hit {fighter['username']} "
#                 f"for **{dmg_taken}** damage! (HP: {fighter['health']})"
#             )
#         else:
#             await ctx.send(f"🌀 {boss['name']} tried **{ability.get('name','attack')}** but missed {fighter['username']}!")

#         # Remove dead players from rotation
#         if fighter["health"] <= 0:
#             await ctx.send(f"💀 {fighter['username']} has been defeated!")
#             alive_pids = [p for p in alive_pids if combatants[p]["health"] > 0]

#         # Reset temporary flags for this player
#         fighter["defending"] = False
#         fighter["dodging"] = False

#         turn += 1

#     # Persist combatant health back to in-memory profiles
#     for pid, c in combatants.items():
#         profile = profiles[pid]
#         profile["health"] = max(0, int(c["health"]))
#         profiles[pid] = profile

#     return boss_hp <= 0

# ## Helper function to grant boss rewards (unlock planet + warpdrive)
# def grant_boss_rewards(user_id: str, planet_id: int, profile: dict):
#     next_planet = planet_id + 1
#     profile["max_unlocked_planet"] = max(profile.get("max_unlocked_planet", 1), next_planet)

#     items = load_json(ITEMS_FILE)
#     warpdrives = items.get("warpdrives", {})

#     inv = profile.get("inventory", {})

#     # Remove old warpdrives
#     for wid in list(inv.keys()):
#         if wid in warpdrives:
#             inv.pop(wid, None)

#     new_warp_id = None
#     for wid, wdata in warpdrives.items():
#         if wdata.get("target_planet") == next_planet:
#             inv[wid] = 1
#             new_warp_id = wid
#             break

#     profile["inventory"] = inv
#     print(f"[DEBUG] grant_boss_rewards -> {user_id}: {profile}")
#     return new_warp_id, warpdrives.get(new_warp_id, {}).get("name")


# ## Helper function to apply defeat penalty
# def apply_defeat_penalty(user_id: str, profile: dict):
#     """Apply penalties for losing a bossfight (in-memory only)."""
#     profile["health"] = 0
#     profile["level"] = max(1, profile.get("level", 1) - 1)
#     profile["xp"] = 0
#     print(f"[DEBUG] apply_defeat_penalty -> {user_id}: {profile}")
#     return profile



# # ====================================================
# # PLAY COMMANDS
# # ====================================================

# # ====== SCAN COMMAND ======
# @bot.command(name="scan", aliases=["sc"])
# @with_profile()
# @requires_oxygen(5)
# async def scan(ctx):
#     """Scan your current location for anomalies and encounter a random enemy."""
#     if not await check_and_set_cooldown(ctx, "scan", 60):
#         return

#     player = ctx.player
#     planet_id = str(player.get("current_planet", 1))
#     planets_data = load_json(PLANETS_FILE).get("planets", {})
#     planet_data = planets_data.get(planet_id, {"scrap_mult": 1, "xp_mult": 1, "materials_mult": 1})
#     rarity_bias = planet_data.get("rarity_bias", {"common":1,"uncommon":1,"rare":1})

#     enemy_key, enemy = choose_random_enemy(player, category="basic")  # add category param if needed

#     if not enemy:
#         await ctx.send(f"{ctx.author.mention}, there are no enemies here.")
#         return

#     combat_result = simulate_combat(player, enemy)

#     embed = discord.Embed(
#         title=f"Scan Result - {enemy['name']}",
#         color=discord.Color.orange()
#     )
#     embed.set_thumbnail(url="https://i.imgur.com/ZQZAc7h.png")
#     embed.set_footer(text=f"Player: {player['username']} | Planet {planet_id}")

#     if combat_result["player_won"]:
#         player["health"] = combat_result["player_hp_left"]

#         # Apply planet scaling to rewards
#         Scrap_earned = int(random.randint(5, 15) * planet_data.get("scrap_mult", 1))
#         xp_earned = int(random.randint(10, 30) * planet_data.get("xp_mult", 1))
#         award_text = award_rewards(ctx, Scrap=Scrap_earned, xp=xp_earned)

#         # Add drops with materials multiplier
#         drops_text = "None"
#         if combat_result["drops"]:
#             inventory = player.get("inventory", {})
#             for drop in combat_result["drops"]:
#                 inventory[drop] = inventory.get(drop, 0) + int(1 * planet_data.get("materials_mult", 1))
#             player["inventory"] = inventory
#             drops_text = ", ".join(combat_result["drops"])

#         embed.add_field(name="Outcome", value=f"✅ You defeated the {enemy['name']}! Consumed 5 Oxygen", inline=False)
#         embed.add_field(name="HP Remaining", value=f"{player['health']} / {get_max_health(player)} ❤️", inline=True)
#         embed.add_field(name="Oxygen Remaining", value=f"{player['oxygen']} / {get_max_oxygen(player)} 🫁", inline=True)
#         embed.add_field(name="Rewards", value=award_text, inline=False)
#         embed.add_field(name="Dropped Items", value=drops_text, inline=False)

#     else:
#         player["health"] = 0
#         old_level = player["level"]
#         player["level"] = max(1, player["level"] - 1)
#         player["xp"] = 0

#         embed.add_field(name="Outcome", value=f"💀 {enemy['name']} defeated you! Consumed 5 Oxygen", inline=False)
#         embed.add_field(name="Level Lost", value=f"Level {old_level} → Level {player['level']}", inline=False)
#         embed.add_field(name="HP Remaining", value=f"{player['health']} / {get_max_health(player)} ❤️", inline=True)

#     save_profile(ctx.author.id, player)
#     await ctx.send(embed=embed)


# # ====== WORK COMMANDS (scavenge, hack, extract, harvest) ======

# WORK_COOLDOWN = 180  # 3 minutes in seconds

# WORK_MATERIALS = {
#     "scavenge": {
#         "drops": [
#             {"material": "plasteel",        "rarity": "common",   "chance": 0.80, "min": 2, "max": 5},
#             {"material": "plasteel_sheet",  "rarity": "uncommon", "chance": 0.15, "min": 1, "max": 2},
#             {"material": "plasteel_bar",    "rarity": "rare",     "chance": 0.049, "min": 1, "max": 1},
#         ]
#     },
#     "hack": {
#         "drops": [
#             {"material": "circuit",    "rarity": "common",   "chance": 0.75, "min": 2, "max": 5},
#             {"material": "microchip",  "rarity": "uncommon", "chance": 0.15, "min": 1, "max": 2},
#             {"material": "processor",  "rarity": "rare",     "chance": 0.05, "min": 1, "max": 1},
#         ]
#     },
#     "extract": {
#         "drops": [
#             {"material": "plasma",         "rarity": "common",   "chance": 0.85, "min": 1, "max": 4},
#             {"material": "plasma_slag",    "rarity": "uncommon", "chance": 0.10, "min": 1, "max": 2},
#             {"material": "plasma_charge",  "rarity": "rare",     "chance": 0.05, "min": 1, "max": 1},
#         ]
#     },
#     "harvest": {
#         "drops": [
#             {"material": "biofiber",   "rarity": "common",   "chance": 0.80, "min": 2, "max": 5},
#             {"material": "biopolymer", "rarity": "uncommon", "chance": 0.15, "min": 1, "max": 2},
#             {"material": "bio_gel",    "rarity": "rare",     "chance": 0.05, "min": 1, "max": 1},
#         ]
#     }
# }

# def choose_material(drops, rarity_bias):
#     adjusted = []
#     total = 0
#     for drop in drops:
#         bias = rarity_bias.get(drop["rarity"], 1.0)
#         adj_chance = drop["chance"] * bias
#         adjusted.append((drop, adj_chance))
#         total += adj_chance

#     roll = random.random()
#     cumulative = 0
#     for drop, adj_chance in adjusted:
#         cumulative += adj_chance / total
#         if roll <= cumulative:
#             qty = random.randint(drop["min"], drop["max"])
#             return drop["material"], qty

#     fallback = adjusted[0][0]
#     return fallback["material"], random.randint(fallback["min"], fallback["max"])


# async def handle_work(ctx, command_name: str):
#     player = ctx.player

#     # ✅ Shared cooldown for all work commands
#     if not await check_and_set_cooldown(ctx, "work", command_cooldowns["work"]):
#         return

#     # Planet multipliers
#     planets_data = load_json(PLANETS_FILE).get("planets", {})
#     planet_id = str(player.get("current_planet", 1))
#     planet_data = planets_data.get(planet_id, {"scrap_mult": 1, "xp_mult": 1, "materials_mult": 1})
#     rarity_bias = planet_data.get("rarity_bias", {"common": 1, "uncommon": 1, "rare": 1})

#     # Pick material from drop table
#     material, qty = choose_material(WORK_MATERIALS[command_name]["drops"], rarity_bias)

#     # Apply planet scaling
#     qty = max(1, int(qty * planet_data.get("materials_mult", 1)))

#     # Update inventory
#     inv = player.get("inventory", {})
#     inv[material] = inv.get(material, 0) + qty
#     player["inventory"] = inv

#     # Scrap + XP scaling
#     scrap_gain = int(random.randint(5, 10) * planet_data.get("scrap_mult", 1))
#     xp_gain = int(random.randint(3, 7) * planet_data.get("xp_mult", 1))
#     player["Scrap"] = player.get("Scrap", 0) + scrap_gain
#     player["xp"] = player.get("xp", 0) + xp_gain

#     await ctx.send(
#         f"{ctx.author.mention} performed **{command_name}** and gathered "
#         f"{qty}x {material}! 💰 {scrap_gain} Scrap | ⭐ {xp_gain} XP. "
#         f"Consumed 10 Oxygen."
#     )

#     save_profile(ctx.author.id, player)


# # === COMMANDS ===
# @bot.command(name="scavenge", aliases=["scav"])
# @with_profile()
# @requires_oxygen(10)
# async def scavenge(ctx):
#     await handle_work(ctx, "scavenge")

# @bot.command(name="hack")
# @with_profile()
# @requires_oxygen(10)
# async def hack(ctx):
#     await handle_work(ctx, "hack")

# @bot.command(name="extract", aliases=["ext"])
# @with_profile()
# @requires_oxygen(10)
# @requires_planet(3)
# async def extract(ctx):
#     await handle_work(ctx, "extract")

# @bot.command(name="harvest", aliases=["harv"])
# @with_profile()
# @requires_oxygen(10)
# @requires_planet(5)
# async def harvest(ctx):
#     await handle_work(ctx, "harvest")


# # ====== RESEARCH COMMAND ======

# RESEARCH_COOLDOWN = 600  # 10 minutes

# @bot.command(name="research", aliases=["res"])
# @with_profile()
# @requires_oxygen(5)
# async def research(ctx):
#     """Ask the player a research question (multiple choice)."""
#     # ✅ Use central cooldown system
#     if not await check_and_set_cooldown(ctx, "research", RESEARCH_COOLDOWN):
#         return

#     player = ctx.player

#     # Load research questions
#     research_data = load_json(RESEARCH_FILE).get("questions", [])
#     if not research_data:
#         await ctx.send("⚠️ No research questions available.")
#         return

#     # Pick a random question
#     question = random.choice(research_data)

#     # Format multiple-choice options
#     choices_text = "\n".join([f"{idx+1}. {opt}" for idx, opt in enumerate(question["choices"])])

#     await ctx.send(
#         f"🧪 **Research Question:**\n{question['question']}\n\n{choices_text}\n\n"
#         f"⏳ You have **15 seconds** to reply with the correct option number!"
#     )

#     def check(m):
#         return m.author.id == ctx.author.id and m.channel == ctx.channel and m.content.isdigit()

#     try:
#         msg = await bot.wait_for("message", timeout=15.0, check=check)
#     except asyncio.TimeoutError:
#         await ctx.send("⌛ Time’s up! Research failed. No XP awarded.")
#         return

#     # Validate answer
#     answer = int(msg.content.strip())
#     correct_answer = question["answer"]  # 1-based index

#     if answer == correct_answer:
#         planets_data = load_json(PLANETS_FILE).get("planets", {})
#         planet_id = str(player.get("current_planet", 1))
#         planet_data = planets_data.get(planet_id, {"xp_mult": 1})

#         # Scale XP with multiplier + small randomness
#         xp_reward = int((question["xp_reward"] + random.randint(1, 10)) * planet_data.get("xp_mult", 1))
#         player["xp"] = player.get("xp", 0) + xp_reward

#         await ctx.send(
#             f"✅ Correct! You successfully completed research!\n"
#             f"You’ve earned ⭐ {xp_reward} XP."
#         )
#     else:
#         await ctx.send(
#             "❌ Incorrect! Research was not successfully completed. "
#             "No XP awarded (cooldown still applies)."
#         )

#     save_profile(ctx.author.id, player)


# # ====== EXPLORE COMMAND ==========
# @bot.command(name="explore", aliases=["exp"])
# @requires_oxygen(25)
# @with_profile()
# async def explore(ctx):
#     """Explore uncharted sectors of space and fight elite enemies (1 hr cooldown)."""
#     if not await check_and_set_cooldown(ctx, "explore", 3600):
#         return

#     player = ctx.player
#     planet_id = str(player.get("current_planet", 1))
#     planets_data = load_json(PLANETS_FILE).get("planets", {})
#     planet_data = planets_data.get(planet_id, {"scrap_mult": 1, "xp_mult": 1, "materials_mult": 1})

#     enemy_key, enemy = choose_random_enemy(player, category="elite")

#     if not enemy:
#         await ctx.send(f"{ctx.author.mention}, there are no elite enemies here.")
#         return

#     combat_result = simulate_combat(player, enemy)

#     embed = discord.Embed(
#         title=f"Exploration Encounter - {enemy['name']}",
#         color=discord.Color.purple()
#     )
#     embed.set_footer(text=f"Player: {player['username']} | Planet {planet_id}")

#     if combat_result["player_won"]:
#         player["health"] = combat_result["player_hp_left"]

#         # Scale rewards with planet multipliers
#         scrap_earned = int(random.randint(50, 100) * planet_data.get("scrap_mult", 1))
#         xp_earned = int(random.randint(80, 150) * planet_data.get("xp_mult", 1))
#         award_text = award_rewards(ctx, Scrap=scrap_earned, xp=xp_earned)

#         # Add drops with material multiplier (if needed)
#         drops_text = "None"
#         if combat_result["drops"]:
#             inventory = player.get("inventory", {})
#             for drop in combat_result["drops"]:
#                 inventory[drop] = inventory.get(drop, 0) + int(1 * planet_data.get("materials_mult", 1))
#             player["inventory"] = inventory
#             drops_text = ", ".join(combat_result["drops"])

#         embed.add_field(name="Outcome", value=f"✅ You defeated the {enemy['name']}! Consumed 25 Oxygen", inline=False)
#         embed.add_field(name="HP Remaining", value=f"{player['health']} / {get_max_health(player)} ❤️", inline=True)
#         embed.add_field(name="Oxygen Remaining", value=f"{player['oxygen']} / {get_max_oxygen(player)} 🫁", inline=True)
#         embed.add_field(name="Rewards", value=award_text, inline=False)
#         embed.add_field(name="Dropped Items", value=drops_text, inline=False)

#     else:
#         # Player lost
#         player["health"] = 0
#         old_level = player["level"]
#         player["level"] = max(1, player["level"] - 1)
#         player["xp"] = 0

#         embed.add_field(name="Outcome", value=f"💀 {enemy['name']} defeated you! Consumed 25 Oxygen", inline=False)
#         embed.add_field(name="Level Lost", value=f"Level {old_level} → Level {player['level']}", inline=False)
#         embed.add_field(name="HP Remaining", value=f"{player['health']} / {get_max_health(player)} ❤️", inline=True)

#     save_profile(ctx.author.id, player)
#     await ctx.send(embed=embed)


# # ====== DAILY COMMAND ==========
# @bot.command(name="daily")
# @with_profile()
# async def daily(ctx):
#     """Claim a daily reward of Scrap, XP, and items (24 hr cooldown)."""
#     if not await check_and_set_cooldown(ctx, "daily", 86400):
#         return

#     Scrap_earned = random.randint(100, 200)

#     # Scale items by planet level
#     med_kits_earned = 5 * ctx.player.get("current_planet", 1)
#     oxy_earned = 5 * ctx.player.get("current_planet", 1)

#     # --- look up item IDs for medkits and oxy tanks ---
#     items_data = load_json(ITEMS_FILE)

#     medkit_id = None
#     oxy_id = None
#     for iid, item in iterate_all_items(items_data):
#         if item.get("name", "").lower() == "medkit":
#             medkit_id = str(iid)
#         if item.get("name", "").lower() == "oxygen tank":
#             oxy_id = str(iid)

#     inv = ctx.player.get("inventory", {})

#     if medkit_id:
#         inv[medkit_id] = inv.get(medkit_id, 0) + med_kits_earned
#     if oxy_id:
#         inv[oxy_id] = inv.get(oxy_id, 0) + oxy_earned

#     ctx.player["inventory"] = inv

#     # award_rewards just for Scrap/XP
#     msg = f"{ctx.author.mention} claimed their daily reward!\n"
#     msg += award_rewards(ctx, Scrap=Scrap_earned)

#     # Append the item gains
#     if medkit_id:
#         msg += f"\n🩹 +{med_kits_earned} Med Kits"
#     if oxy_id:
#         msg += f"\n🫧 +{oxy_earned} Oxygen Tanks"

#     await ctx.send(msg)


# # ====================================================
# # DEBUG COMMANDS
# # ====================================================
# # @bot.command()
# # async def register(ctx):
# #     """Force-create your profile (for testing)."""
# #     player = get_player(ctx.author.id, ctx.author.name)
# #     await ctx.send(f"Registered profile for **{player['username']}** (Level {player['level']}).")

# # @bot.command()
# # async def filedebug(ctx):
# #     """Show debug info about the file location."""
# #     await ctx.send(f"cwd: `{os.getcwd()}`\nplayers_file: `{PLAYERS_FILE}`")

# @bot.command()
# async def test_save(ctx):
#     players = load_players()
#     players["test"] = {"foo": "bar"}
#     save_players(players)
#     await ctx.send("✅ Wrote test player to file!")


# # ====================================================
# # RUN BOT
# # ====================================================
# if __name__ == "__main__":
#     # Run a batch migration to ensure old players get the new fields (safe)
#     #migrate_all_profiles()
#     migrate_players_file()
#     #migrate_currency_to_Scrap()

#     # start the bot (uncomment & insert your token)
#     # bot.run("YOUR_TOKEN")

#     bot.run("MTQxNjQzNzI1NTg2NTg5Mjk3OA.GBwLhc.jAsdOXJ9tkmH1FxctS1ssHyK8kiQnrEPrD7RSM")


