# Cogs & Command Modules

Covers all Discord cogs in `cogs/` directory.

## Cog Manifest
1. `cogs/code_redeem.py`:
   - Game gift code batch redemption via parallel worker tasks.
   - Deferral handling and interactive result embeds.
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
9. `cogs/menu.py`:
   - Interactive help navigation and menu panels.

## Cog Development Invariants
- Each cog must end with `async def setup(bot): await bot.add_cog(CogName(bot))`.
- Defer slash command interactions immediately when operations exceed 2s.
- UI elements (buttons, selects) must use `utils/views.py` classes.

