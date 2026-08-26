# Discord Game Utility Bot - Project Guidelines

## Core Stack & Architecture
- **Environment**: Python 3.12, `discord.py` (v2.x) with async app commands (slash commands).
- **Non-blocking I/O**:
  - Use `aiosqlite` for database queries (databases stored in `data/`).
  - Use `aiohttp` for HTTP requests inside async routines (avoid blocking `requests` inside the event loop).
- **Directory Layout**:
  - `cogs/` — Modular bot extensions loaded dynamically in `main.py` via `setup_hook`. Each cog implements `async def setup(bot)`.
  - `databases/` — Encapsulated SQLite data access classes (`player_database.py`, `wyr_database.py`). Cogs call database methods rather than executing raw SQL directly.
  - `utils/` — Reusable components:
    - `utils/embeds.py` — Discord embed builders and visual formatting.
    - `utils/views.py` — Interactive Discord UI views, buttons, dropdowns.
    - `utils/modals.py` — Form modals.
    - `utils/google_sync.py` / `utils/redeem_code.py` / `utils/countdown.py` — Domain utility modules.

## Discord Interaction & Error Handling
- **Defer long operations**: Call `await interaction.response.defer(ephemeral=...)` immediately if an operation involves network requests, code redemption, Google sync, or disk/database delays (>2s).
- **Interaction expiration**: Always verify `if not interaction.response.is_done():` before responding.
- **View message binding**: When a view depends on persistent updates, assign the returned message object (`view.message = message`).
- **User feedback**: Provide clear, ephemeral error embeds for invalid inputs, missing permissions, or rate-limit issues. Guard owner commands with `@commands.is_owner()` and admin actions with `@app_commands.checks.has_permissions()`.

---

## Code Index (Codegraph)
- When `.codegraph/` index exists, prioritize `codegraph_explore` for:
  - Architecture overview and subsystem navigation.
  - Symbol references, call hierarchies, and blast radius before edits.
  - Cross-module flow tracing (`cogs` -> `databases` -> `utils`).
- Trust codegraph AST results; avoid redundant grep/read operations when codegraph returns exact definitions and references.

---

## Serena Memory Management
- **Location**: `.serena/memories/`
- **Entry Point**: `mem:core` is the root graph memory referencing domain-specific memories (`mem:architecture`, `mem:database`, `mem:cogs`, etc.).
- **Progressive Discovery**: Use `mem:<path>` syntax inside backticks to link related memories.
- **Style**: Terse, invariant-focused agent notes. Record durable conventions, API schemas, and architectural boundaries rather than temporary task details.
- **Maintenance**: Update memory files whenever core schemas, database models, cog interfaces, or key external integrations change.

