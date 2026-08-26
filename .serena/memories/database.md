# Database Layer & Schema Design

Covers SQLite database access via `aiosqlite`. Databases reside in `data/`.

## Data Access Modules (`databases/`)

### 1. `Player_Database` (`databases/player_database.py`)
- Target: `data/players.db`
- Primary Tables:
  - `players`: User game profile, player IDs, nicknames, alliances, server/state IDs.
  - `guild_settings`: Per-guild configuration (channels, admin roles, sync parameters).
  - `redemption_history`: Tracks redeemed codes per player to prevent duplicate attempts.
- Invariant: Encapsulate all player queries in `Player_Database` methods. Do not write raw SQL in cogs.

### 2. `Question_Database` (`databases/wyr_database.py`)
- Target: `data/wyr_question_bank.db`
- Primary Table: `wyr_questions` (id, option_a, option_b, option_a_count, option_b_count).
- Methods: `init_db()`, `get_random_wyr_question()`, `increment_wyr_choice()`.

## SQLite Async Invariants
- Always use `async with aiosqlite.connect(...)` or connection helper.
- Commit transactions inside `async with db.cursor()` context.

