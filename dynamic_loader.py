import os

def _file_has_setup(module_path: str) -> bool:
    try:
        with open(module_path, "r", encoding="utf-8") as f:
            src = f.read()
        return ("async def setup(" in src) or ("def setup(" in src)
    except Exception:
        return False

async def load_all_extensions(bot):
    """
    Dynamically loads all command and system modules (Cogs) into the bot.
    Only loads files that actually define a setup() function.
    Also explicitly loads core.guards (global checks/locks).
    """
    base_dirs = ["commands", "systems"]
    loaded, failed, skipped = [], [], []

    for base_dir in base_dirs:
        for root, _, files in os.walk(base_dir):
            for file in files:
                if not file.endswith(".py") or file.startswith("__"):
                    continue

                module_path = os.path.join(root, file)
                if not _file_has_setup(module_path):
                    skipped.append(module_path)
                    continue

                module_name = module_path.replace(os.sep, ".").replace(".py", "")

                try:
                    await bot.load_extension(module_name)
                    print(f"[✅] Loaded {module_name}")
                    loaded.append(module_name)
                except Exception as e:
                    print(f"[❌] Failed to load {module_name}: {type(e).__name__}: {e}")
                    failed.append((module_name, str(e)))

    # Explicitly load global guards (registers bot.add_check)
    try:
        await bot.load_extension("core.guards")
        print("[✅] Loaded core.guards")
        loaded.append("core.guards")
    except Exception as e:
        print(f"[❌] Failed to load core.guards: {type(e).__name__}: {e}")
        failed.append(("core.guards", str(e)))

    print(f"\n[🧩] Loaded {len(loaded)} extensions ({len(failed)} failed, {len(skipped)} skipped - no setup)")
    if failed:
        print("[⚠️] Failed modules:")
        for name, error in failed:
            print(f"   - {name}: {error}")

    # Log all commands registered with the bot
    print(f"[🧠] Commands loaded: {[c.name for c in bot.commands]}")