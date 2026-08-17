# Architecture & Subsystems

## 1. Bot Entrypoint
- `main.py`: Initializes `DiscordGameUtilityBot` with `commands.when_mentioned_or("n!")`, full intents, and owner ID. Automatically runs `Question_Database.init_db()` and dynamically loads all cogs in `cogs/`. Single-instance process file locking.

## 2. Cogs (`cogs/`)
- `player_manager.py`: Slash commands (`/player list`, `/player edit`, `/player add`, `/player search`, `/player flagged`, `/player unflag`, `/player prune-flagged`, `/player stats`, `/player export`, `/player import`, `/player sync-names`). Interactive paginated views, modals with live API verification, and Century Games player nickname auto-sync.
- `code_redeem.py`: Slash commands (`/redeem-for-all`, `/redeem-for-player`, `/redeem-history`, `/redeem-scan-history`). Background task execution, confirmation views, live progress updates, and webhook fallback.
- `battle_tactics.py`: Slash command (`/reinforcement-timing`) and prefix command (`n!reinforce`) for calculated castle garrison reinforcement timing between incoming enemy rallies with visual timeline embeds.
- `menu.py`: Main interactive menu entrypoint (`/menu`).
- `rally_countdown.py`: Rally voice countdowns (`/rally-countdown`, `/rally-join`, `/rally-stop`, `/rally-menu`). Voice state update listener for automatic disconnect when empty.
- `wyr.py`: Would You Rather voting games.
- `roast.py`: Fun roast commands.

## 3. Databases (`databases/` and `data/`)
- `player_database.py`: Async SQLite manager for `players` and `redeemed_codes` tables in `data/players.db`.
  - Tables: `players` (`fid`, `kid`, `name`, `alliance`, `status`, `warning_count`, `warning_reason`, timestamps) and `redeemed_codes` (`code`, `redeemed_at`, `redeemed_by`, `success_count`, `total_attempted`).
- `wyr_database.py`: Async SQLite manager for `wyr_questions`, `tags`, and `question_tags` in `data/wyr_question_bank.db`.

## 4. Utilities (`utils/`)
- `redeem_code.py`: Century Games API HTTP client with MD5 salt hashing (`mN4!pQs6JrYwV9`), header randomization, `verify_player` validator, and batch redemption engine with live progress callbacks and automatic SQLite strike logging.
- `countdown.py`: Audio generation via `gTTS`/FFmpeg, voice client connections, voice playback, and idle disconnect timer scheduling.
- `code_detector.py`: Sniffer and parser for official Kingshot announcement channels (`1374889273077272636`, `1374888983812902993`, `1374888701204758599`), unredeemed code deduplication check, and 1-click interactive alert embed generation.
- `embeds.py`: Discord embed templates (`MainMenuEmbed`, `WyrEmbed`).
- `views.py`: Discord UI views (`MenuButtons`, `PlayerMenuButtons`, `UtilityMenuButtons`, `GameMenuButtons`, `RallyCountdownView`, `WyrButtons`).
- `modals.py`: Discord UI modals (`RedeemModal`, `RedeemSingleModal`, `CustomCountdownModal`, `SearchPlayerModal`).
