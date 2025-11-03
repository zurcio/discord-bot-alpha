import traceback
from functools import wraps
from discord.ext import commands
from core.players import load_profile, save_profile, default_profile, migrate_player
from core.utils import get_max_health, get_max_oxygen
from systems.oxygenregen import apply_oxygen_regen
from core.sector import ensure_sector
from core.skills_hooks import is_player_overcharged


def requires_profile(auto_save=True):
    """Require an existing profile; if present, migrate + regen, attach to ctx, clamp and save after."""
    def inner(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Support cog methods and plain commands
            ctx = args[1] if len(args) > 1 and hasattr(args[1], "author") else args[0]
            uid = str(ctx.author.id)
            try:
                profile = load_profile(uid)
                if not profile:
                    await ctx.send(
                        "👋 Welcome! You don’t have a profile yet.\n"
                        "Use `!start` to register and begin playing. After that, try: `scan`, `research`, `explore`.\n"
                        "Tip: Use `!tutorial` next for a quick guide."
                    )
                    return

                # Match with_profile lifecycle (minus auto-create)
                username = getattr(ctx.author, "name", str(ctx.author))
                profile = migrate_player(profile, uid, username)
                profile = apply_oxygen_regen(profile)
                ctx.player = profile

                result = await func(*args, **kwargs)

                # Clamp and save like with_profile
                try:
                    ctx.player["health"] = min(
                        ctx.player.get("health", 0), get_max_health(ctx.player)
                    )
                    ctx.player["oxygen"] = min(
                        ctx.player.get("oxygen", 0), get_max_oxygen(ctx.player)
                    )
                except Exception as e:
                    print(f"[requires_profile] Clamp warning: {e}")

                if auto_save:
                    save_profile(uid, ctx.player)

                return result
            except Exception as e:
                print(f"[❌ requires_profile error] {type(e).__name__}: {e}")
                traceback.print_exc()
                try:
                    await ctx.send(f"⚠️ Internal profile error: {type(e).__name__}: {e}")
                except Exception:
                    pass
        return wrapper
    return inner

# def with_profile(auto_save=True):
#     def decorator(func):
#         @wraps(func)
#         async def wrapper(self, ctx, *args, **kwargs):
#             try:
#                 uid = str(ctx.author.id)
#                 username = getattr(ctx.author, "name", str(ctx.author))

#                 # Load or create profile
#                 player = load_profile(uid)
#                 if not player:
#                     player = default_profile(uid, username)
#                     save_profile(uid, player)

#                 # Migration and oxygen regen
#                 player = migrate_player(player, uid, username)
#                 player = apply_oxygen_regen(player)
#                 ctx.player = player

#                 # Execute the actual command
#                 result = await func(self, ctx, *args, **kwargs)

#                 # Clamp and save safely
#                 try:
#                     ctx.player["health"] = min(
#                         ctx.player.get("health", 0), get_max_health(ctx.player)
#                     )
#                     ctx.player["oxygen"] = min(
#                         ctx.player.get("oxygen", 0), get_max_oxygen(ctx.player)
#                     )
#                 except Exception as e:
#                     print(f"[with_profile] Clamp warning: {e}")

#                 if auto_save:
#                     save_profile(uid, ctx.player)
#                 return result

#             except Exception as e:
#                 print(f"[❌ with_profile error] {type(e).__name__}: {e}")
#                 import traceback
#                 traceback.print_exc()
#                 try:
#                     await ctx.send(f"⚠️ Internal profile error: {type(e).__name__}: {e}")
#                 except Exception:
#                     pass

#         return wrapper
#     return decorator

def requires_oxygen(amount):
    def decorator(func):
        @wraps(func)
        async def wrapper(self, ctx, *args, **kwargs):
            player = getattr(ctx, "player", None)
            if not player or player.get("oxygen", 0) < amount:
                await ctx.send(f"{ctx.author.mention}, you don’t have enough oxygen!")
                return
            player["oxygen"] -= amount
            return await func(self, ctx, *args, **kwargs)
        return wrapper
    return decorator

def requires_planet(min_planet):
    def decorator(func):
        @wraps(func)
        async def wrapper(self, ctx, *args, **kwargs):
            player = getattr(ctx, "player", None)
            if not player:
                await ctx.send(f"{ctx.author.mention}, you must reach Planet {min_planet} to use this command!")
                return
            # NEW: Overcharged bypasses planet requirement
            if not is_player_overcharged(player):
                if player.get("max_unlocked_planet", 1) < min_planet:
                    await ctx.send(f"{ctx.author.mention}, you must reach Planet {min_planet} to use this command!")
                    return
            return await func(self, ctx, *args, **kwargs)
        return wrapper
    return decorator


def requires_sector(min_sector: int):
    """Require the player to be at least a given Sector."""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, ctx, *args, **kwargs):
            player = getattr(ctx, "player", None)
            if not player:
                await ctx.send(f"{ctx.author.mention}, you don’t have a profile loaded.")
                return
            sector = ensure_sector(player)
            if sector < int(min_sector):
                await ctx.send(f"{ctx.author.mention}, you must reach Sector {min_sector} to use this command! (Current: Sector {sector})")
                return
            return await func(self, ctx, *args, **kwargs)
        return wrapper
    return decorator
