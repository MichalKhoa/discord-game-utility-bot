# Architecture & Structure

## Entry Point
- `main.py`: Initializes `discord.ext.commands.Bot` with message content & voice intents, registers slash commands, loads cogs dynamically on startup.

## Cogs (`cogs/`)
- `code_redeem.py`: Gift code redemption command handling & UI views.
- `rally_countdown.py`: Rally / castle battle timing and audio triggers.
- `menu.py`: Main interactive help and action menus.
- `wyr.py`: Would-you-rather game handlers.
- `roast.py`: Fun roast commands.

## Utilities (`utils/`)
- `redeem_code.py`: Century Games gift code API client (`https://wos-giftcode.centurygame.com/api/player` & `.../api/gift_code`). Computes MD5 salt signatures.
- `castle_battle_support.py` & `countdown.py`: Audio voice client timer and visual embed updates.
- `embeds.py`, `views.py`, `modals.py`: Discord UI components.

## Data Layer (`databases/` and root)
- `databases/wyr_database.py`: SQLite wrapper for WYR queries.
- `playerIDs.txt`, `redeemed_codes.txt`: Local state persistence for gift codes.
- `service-account.json`: Google Cloud credentials for Google Sheets player ID sync.
