# Discord Game Utility Bot

Modular, high-performance Discord utility bot built with Python 3.12, `discord.py` (v2.x), `aiosqlite`, and `aiohttp`.

---

## Features

- **🎯 Coordle (Co-op Wordle)**:
  - Cooperative multi-player Wordle game with configurable word lengths (4–8) and attempts (4–12).
  - Standard mode and speedrun Blitz mode with live timeout watchers.
  - Pillow board and QWERTY keyboard image generator (`utils/coordle_image.py`).
  - Dictionary API & Datamuse definition lookups on win, loss, or surrender.
  - Global daily puzzle at 00:00 UTC and multi-round multiplayer sessions.
- **👥 Player & Alliance Manager**:
  - Map game IDs (FID), nicknames, and alliance roles to Discord accounts.
  - Interactive paginated roster views with alliance and status filters.
  - CSV import/export, batch editing, and automatic duplicate detection.
- **🎁 Automated Gift Code Redeemer**:
  - High-concurrency gift code batch redemption with proxy pooling (`utils/redeem_code.py`).
  - Announcement channel monitoring with regex code detector (`utils/code_detector.py`).
  - Audit logging, status embeds, and abort controls.
- **🎲 Russian Roulette**:
  - Turn-based revolver game (solo vs bot or multiplayer lobbies).
  - Animated GIF rendering for spin, safe, and bang outcomes (`assets/roulette/`).
- **🗳️ Would You Rather (WYR)**:
  - Interactive community poll questions with live ASCII vote percentage bars and persistent tallying.
- **⏱️ Rally Countdown & Voice**:
  - Synchronized voice channel voice countdowns (`gTTS` audio synthesis) and text timer alerts.
- **💾 Automated Backups & Google Sync**:
  - Daily SQLite database snapshot uploads to designated Discord channels and Google Drive folders.
  - Bidirectional roster synchronization with Google Sheets.

---

## Directory Structure

```
discord-game-utility-bot/
├── cogs/                  # Discord slash command extensions loaded dynamically
│   ├── backup_sync.py     # Database backup & Google Sheets sync commands
│   ├── battle_tactics.py  # Reinforcement timing calculations
│   ├── code_redeem.py     # Gift code redemption commands & auto-scanner
│   ├── coordle.py         # Coordle game & session commands
│   ├── menu.py            # Interactive help and feature navigation
│   ├── player_manager.py  # Alliance & player management commands
│   ├── rally_countdown.py # Audio/text countdown timers
│   ├── roast.py           # Fun humor & roast commands
│   ├── russian_roulette.py# Russian roulette revolver game
│   └── wyr.py             # "Would You Rather" polls
├── databases/             # Encapsulated SQLite data access classes
│   ├── coordle_database.py
│   ├── player_database.py
│   └── wyr_database.py
├── utils/                 # Reusable domain utilities, embeds, and UI views
│   ├── code_detector.py   # Regex-based gift code parser
│   ├── coordle_image.py   # Pillow image board generator
│   ├── countdown.py       # Audio generation & voice playback
│   ├── embeds.py          # Discord embed formatting helpers
│   ├── google_sync.py     # Google Drive & Sheets API client
│   ├── modals.py          # Discord form modals
│   ├── redeem_code.py     # HTTP client, proxy pool, and batch engine
│   └── views.py           # Discord UI buttons, dropdowns, and paginators
├── assets/                # Static assets (images, gifs for games)
├── audio/                 # Cached voice synthesis audio files
├── data/                  # SQLite databases and local backup snapshots
├── tests/                 # Unit and integration test suite
├── Dockerfile             # Docker container configuration
├── docker-compose.yml     # Container orchestration stack
├── GEMINI.md              # Project developer guidelines & conventions
└── requirements.txt       # Python dependencies
```

---

## Getting Started

### Prerequisites
- **Python 3.12+**
- **FFmpeg** & **libopus** (required for voice countdowns and audio playback)
  - Ubuntu/Debian: `sudo apt install ffmpeg libopus0`
  - Windows: Ensure `ffmpeg.exe` is in your `PATH`

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/MichalKhoa/discord-game-utility-bot.git
   cd discord-game-utility-bot
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

### Configuration Variables

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | Yes | Discord bot application token (or place in `token.txt`). |
| `BACKUP_CHANNEL_ID` | No | Discord channel ID to receive automated SQLite backups. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | No | Raw JSON service account key for Google Drive/Sheets sync. |
| `GOOGLE_DRIVE_FOLDER_ID` | No | Google Drive target folder ID for database snapshots. |
| `GOOGLE_SHEET_ID` | No | Google Sheet ID or URL for roster synchronization. |
| `PROXY_LIST` | No | Comma-separated list of HTTP/HTTPS proxies (`http://ip:port`). |

### Running the Bot

Directly with Python:
```bash
python main.py
```

Using Docker Compose:
```bash
docker compose up -d --build
```

---

## Testing

Run the automated test suite using `unittest`:
```bash
python -m unittest discover tests
```

---

## Slash Commands Overview

| Category | Primary Commands |
|---|---|
| **Coordle** | `/coordle`, `/coordle_daily`, `/coordle_leaderboard`, `/coordle_stats`, `/coordle_rules`, `/coordle_session` |
| **Player Roster** | `/player list`, `/player add`, `/player edit`, `/player search`, `/player flagged`, `/player export-csv`, `/player sync-doc` |
| **Gift Codes** | `/redeem`, `/redeem-for-all`, `/redeem-for-player`, `/redeem-stop`, `/redeem-history`, `/redeem-watch-channel` |
| **Games** | `/roulette`, `/wyr` |
| **Utility** | `/rally`, `/menu`, `/backup`, `/sync-sheet`, `/reinforce` |
| **Admin** | `!sync`, `!reload`, `!reload_util` |
