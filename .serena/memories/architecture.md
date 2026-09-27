# System Architecture & Bot Lifecycle

Details the bot entry point, extension loading mechanism, and interaction flows.

## Entry Point (`main.py`)
- `DiscordGameUtilityBot(commands.Bot)`: Subclassed bot with `command_prefix="n!"` and `Intents.all()`.
- `setup_hook()`:
  - Initializes all database singletons (`bot.wyr_db`, `bot.player_db`, `bot.coordle_db`) via `await *.init_db()`.
  - Dynamically loads all cogs in `cogs/*.py` via `bot.load_extension()`. Cogs reuse these shared instances.
- `acquire_lock()`: Cross-platform single-instance lock (`fcntl.lockf` on Linux, `msvcrt.locking` on Windows).
- `on_ready()`:
  - Loads Opus audio library (`libopus.so.0`).
  - Checks optional `davey` package for Discord voice E2EE.

## UI View Lifecycle
- Standard interactive views inherit from `BaseView` (`utils/views.py`).
- Automated `on_timeout`: Disables child buttons/selects and updates `self.message`.
- Guard `interaction_check` with `not self.is_finished()`.

## Slash Command & Sync Flow
- Hybrid command model: Slash commands via `@app_commands.command()` in cogs; prefix command `!sync` / `n!sync` in `main.py` for global/guild command tree sync.

## Non-blocking I/O Invariant
- Async handlers must not block event loop. Avoid synchronous `requests` inside cogs or utils; use `aiohttp` or offload blocking CPU/IO tasks.
