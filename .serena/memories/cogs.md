# Cogs & Command Modules

Covers all Discord cogs in `cogs/` directory.

## Cog Manifest
1. `cogs/code_redeem.py`:
   - Game gift code batch redemption via parallel worker tasks.
   - Real-time automated code detection from announcement channels and periodic/startup scanner.
   - Automated batch redemption dispatch for unredeemed codes with queue/lock handling.
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
7. `cogs/battle_tactics.py`:
   - Tactical battle support calculations and strategic suggestions.
8. `cogs/roast.py`:
   - Voice/text humor roast commands.
9. `cogs/coordle.py`:
   - Cooperative multi-player Wordle game with custom word lengths (4-8) and attempt limits (4-12).
   - Word lists partitioned from `data/wordle/` (answers and comprehensive guesses).
   - Modal input validation, non-punitive invalid word feedback, and standard duplicate letter handling.
   - Base-5 anti-sniping scoring formula: 🟨 +5, 🟩 +10, 🎯 Solve: `Letters Left to Guess × 5`, 🏆 Team Win: +10.
   - Commands: `/coordle`, `/coordle_leaderboard`, `/coordle_stats`, `/coordle_rules`.
10. `cogs/menu.py`:
   - Interactive help navigation and menu panels.

## Cog Development Invariants
- Each cog must end with `async def setup(bot): await bot.add_cog(CogName(bot))`.
- Defer slash command interactions immediately when operations exceed 2s.
- UI elements (buttons, selects) must use `utils/views.py` classes.

