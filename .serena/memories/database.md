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
- Primary Table: `wyr_questions` (id, option_a, option_b, rating, votes_a, votes_b).
- Methods: `init_db(seed_defaults)`, `get_random_wyr_question()`, `record_wyr_vote(question_id, choice)`, `add_wyr_question(...)`.

### 3. `CoordleDatabase` (`databases/coordle_database.py`)
- Target: `data/coordle.db`
- Primary Tables:
  - `coordle_stats`: `user_id`, `guild_id`, `user_name`, `points`, `games_played`, `games_won`, `words_solved`, `total_guesses`, `green_discovered`, `yellow_discovered`, `current_streak`, `max_streak`, `last_daily_date`, PRIMARY KEY(user_id, guild_id).
  - `coordle_guild_channels`: `guild_id`, `daily_channel_id`.
  - `coordle_definitions`: `word` PRIMARY KEY, `definition`, `created_at`.
- Methods: `init_db()`, `add_points_and_stats(...)`, `get_user_stats(...)`, `get_user_rank(...)`, `get_leaderboard(...)`, `update_daily_streak(...)`, `set_daily_channel(...)`, `get_daily_channel(...)`, `get_all_daily_channels(...)`, `remove_daily_channel(...)`, `get_definition(word)`, `save_definition(word, definition)`.

## SQLite Async Invariants
- Always use `async with aiosqlite.connect(...)` or connection helper.
- Commit transactions inside `async with db.cursor()` context.

