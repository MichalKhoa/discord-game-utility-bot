# Discord Game Utility Bot - Core Memory

Root graph memory for discord-game-utility-bot.

## Domain Memories
- **System Architecture & Bot Lifecycle**: `mem:architecture`
- **Database Layer & Schema Design**: `mem:database`
- **Cogs & Slash Command Modules**: `mem:cogs`
- **External Integrations & Voice**: `mem:integrations`
- **Memory Invariants & Maintenance**: `mem:memory_maintenance`

## Tech Stack Invariants
- Python 3.12, `discord.py` 2.x
- Non-blocking I/O: `aiosqlite` for database, `aiohttp` for async HTTP
- SQLite storage in `data/`
- Discord UI components in `utils/` (views, modals, embeds)

