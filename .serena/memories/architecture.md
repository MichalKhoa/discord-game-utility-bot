# System Architecture & Bot Lifecycle

Details the bot entry point, extension loading mechanism, and interaction flows.

## Entry Point (`main.py`)
- `DiscordGameUtilityBot(commands.Bot)`: Subclassed bot with `command_prefix="n!"` and `Intents.all()`.
- `setup_hook()`:
  - Initializes database (`bot.database = Question_Database()`, `await bot.database.init_db()`).
  - Dynamically loads all cogs in `cogs/*.py` via `bot.load_extension()`.
- `on_ready()`:
  - Loads Opus audio library (`libopus.so.0`).
  - Checks optional `davey` package for Discord voice E2EE.

## Slash Command & Sync Flow
- Hybrid command model: Slash commands via `@app_commands.command()` in cogs; prefix command `!sync` / `n!sync` in `main.py` for global/guild command tree sync.

## Non-blocking I/O Invariant
- Async handlers must not block event loop. Avoid synchronous `requests` inside cogs or utils; use `aiohttp` or offload blocking CPU/IO tasks.
