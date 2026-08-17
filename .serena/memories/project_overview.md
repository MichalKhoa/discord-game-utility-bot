# Discord Game Utility Bot

Discord utility bot built with `discord.py` for game community management (Whiteout Survival / Century Games).

## Core Features
- **Gift Code Redemption**: Automated multi-player code redemption against game API with MD5 signature hashing and Google Sheets player sync.
- **Rally & Castle Countdown**: Synchronized audio countdown in voice channels and interactive Discord embeds.
- **Interactive UI**: Discord views, modals, select menus.
- **WYR (Would You Rather)**: Interactive mini-game with SQLite question storage.
- **Roast Cog**: Voice/text entertainment features.

## Runtime & Stack
- Python 3.12+
- `discord.py` (cogs, slash commands, UI components)
- `gspread` (Google Sheets player management)
- `sqlite3` (local databases)
- `docker-compose` / `Dockerfile` containerization support
