# Discord Game Utility Bot

Discord utility bot built with `discord.py` for game community management (Whiteout Survival / Century Games).

## Core Modules & Features
- **Player Registry & Database (`databases/player_database.py`)**:
  - SQLite backend (`data/players.db`) for player IDs (`fid`), Kingdom IDs (`kid`), in-game names, and alliance groupings.
  - Auto-migrates legacy text IDs on startup.
  - Real-time API verification on player add/edit.
  - Strike-based flagging system (`ACTIVE`, `FLAGGED`, `DISABLED`) replacing legacy exception text files.
- **Gift Code Redemption (`cogs/code_redeem.py`, `utils/redeem_code.py`)**:
  - Multi-code and single-player redemption against Century Games API with dynamic MD5 signing and browser header rotation.
  - Database-backed redeemed code history with interactive confirmation prompts on re-redeeming previously used codes.
  - Long-running live progress bar with visual indicator, completion percentage, active counters, and dynamic ETA updates.
  - Webhook delivery with automatic graceful fallback to direct channel messages.
- **Rally & Castle Voice Countdown (`cogs/rally_countdown.py`, `utils/countdown.py`)**:
  - Synchronized audio countdowns (6s to 20s and custom seconds) and interactive visual embeds.
  - Voice channel auto-disconnect after 5 minutes of idle inactivity and instant leave when human members leave the channel.
- **Interactive UI Menu (`cogs/menu.py`, `utils/views.py`, `utils/modals.py`)**:
  - Modular Discord menu with sub-menus for Games, Players (paginated list, modals, search, stats, export), and Utilities.
- **Would You Rather Game (`cogs/wyr.py`, `databases/wyr_database.py`)**:
  - Interactive mini-game with SQLite question storage.
- **Roast Cog (`cogs/roast.py`)**: Voice and text entertainment features.

## Runtime & Deployment
- Python 3.12 (`python:3.12-slim` Docker image)
- `discord.py`, `aiosqlite`, `requests`, `aiohttp`, `gtts`, `PyNaCl`, `davey`
- Docker Compose with persistent volume mounts (`./data:/app/data`, `./audio:/app/audio`)
