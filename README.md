# Discord Bot Alpha

A modular Discord bot with skills, combat, lootboxes, crafting, raids, and more. Commands are organized as cogs under `commands/` and systems under `systems/`.

## Features
- Modular command cogs (bank, craft, combat, explore/scan, ship, tinker, raids, etc.)
- Skills system (worker, crafter, tinkerer, trader, boxer, gambler, soldier) with perks
- Lootboxes with planet gating and rarities (up to universal)
- Raids MVP (battery, timed boss fights, proportional rewards)

## Requirements
- Python 3.10+

## Setup
1. Clone the repo and enter the folder.
2. (Recommended) Create a virtual environment.
3. Install dependencies:
   
   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Configure your environment:
   - Copy `.env.example` to `.env` and set `DISCORD_TOKEN` to your bot token.

## Run
```powershell
python bot.py
```

On startup, the bot loads all cogs via `dynamic_loader.load_all_extensions`.

## Development notes
- Runtime JSON data (`data/players.json`, `data/cooldowns.json`, `data/raids.json`) is ignored and not tracked.
- Never commit secrets (like your Discord bot token). Use `.env` for local development and keep it out of Git.

## Security
If a token was ever committed to this repository:
- Immediately rotate the token in the Discord Developer Portal.
- Consider purging the token from Git history using `git filter-repo` or BFG Repo-Cleaner, then force push.

## License
Add a license of your choice (e.g., MIT) by creating a `LICENSE` file.
