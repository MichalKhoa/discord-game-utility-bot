# Cogs & Command Modules

Covers all Discord cogs in `cogs/` directory.

## Cog Manifest
1. `cogs/code_redeem.py`:
   - Game gift code batch redemption via parallel worker tasks.
   - Real-time automated code detection from announcement channels and periodic/startup scanner.
   - Automated batch redemption dispatch for unredeemed codes with queue/lock handling (reports to channel `1374873047127035981` by default).
   - Commands: `/redeem-for-all`, `/redeem-for-player`, `/redeem-stop`, `/redeem-history`, `/redeem-scan-history`, `/redeem-set-channel`, `/redeem-watch-channel`.
2. `cogs/player_manager.py`:
   - Player registration, linking game ID to Discord user, alliance roster management.
   - Interactive paginated views: `PlayerListView` (with dynamic alliance/status dropdown filter) and `FlaggedPlayersView`.
3. `cogs/backup_sync.py`:
   - Backup/restore mechanisms and automated sync to Google Sheets.
4. `cogs/rally_countdown.py`:
   - Dynamic voice/text rally timer countdowns and sound generation via `gTTS` / `audio/`.
5. `cogs/wyr.py`:
   - "Would you rather" interactive game with real-time ASCII progress bar voting and global vote persistence.
6. `cogs/russian_roulette.py`:
   - Interactive turn-based revolver duel (solo or multiplayer lobby) with visual cylinder status.
   - Core game engine and view encapsulated in `utils/roulette_views.py` (`RussianRouletteGame`, `RussianRouletteView`).
   - Active view dynamically moves down chat on turns, timeouts, and player actions by deleting the previous message and posting fresh at the bottom.
   - Animated GIF assets in `assets/roulette/`.
7. `cogs/battle_tactics.py`:
   - Tactical battle support calculations and strategic suggestions.
8. `cogs/roast.py`:
   - Voice/text humor roast commands.
9. `cogs/coordle.py`:
   - Cooperative multi-player Wordle game with custom word lengths (4-8), attempt limits (4-12), and Standard / Blitz speedrun modes.
   - Core game engine and dictionary lookups encapsulated in `utils/coordle_logic.py` (`CoordleGame`, `CoordleSession`).
   - Interactive views and guess modal encapsulated in `utils/coordle_views.py` (`CoordleGameView`, `CoordleGuessModal`, `CoordleLeaderboardView`).
   - Dynamic Pillow (`utils/coordle_image.py`) board & QWERTY keyboard image renderer.
   - Deterministic server-wide daily puzzles (/coordle_daily) and automated 00:00 UTC channel broadcasting.
   - Periodic 30-minute puzzle spawning at :00 and :30 with configurable role mentions, word length (or random), attempts, and timeout expiration for overlapping games.
   - Word lists live in `assets/wordle/` (`answers_*.json`, `guesses_*.json`); answers are curated common words validated via `scripts/check_word_lists.py`.
   - Commands: `/coordle`, `/coordle_daily`, `/coordle_daily_channel`, `/coordle_spawn_channel`, `/coordle_leaderboard`, `/coordle_stats`, `/coordle_rules`, `/coordle_session`.
10. `cogs/menu.py`:
   - Interactive help navigation and menu panels.

## Cog Development Invariants
- Each cog must end with `async def setup(bot): await bot.add_cog(CogName(bot))`.
- Defer slash command interactions immediately when operations exceed 2s.
- UI views and modals live in `utils/views.py`, `utils/modals.py`, or dedicated `utils/*_views.py` modules; cogs import them rather than inlining UI definitions.

