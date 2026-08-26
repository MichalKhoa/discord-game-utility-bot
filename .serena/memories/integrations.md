# External Integrations & Voice

Covers third-party services, voice processing, and external API flows.

## 1. Google Sheets Sync (`utils/google_sync.py`)
- Libraries: `gspread`, `google-auth`, `google-api-python-client`.
- Service Account Credentials: `credentials.json` (or configured environment credentials).
- Role: Syncs registered players and alliance rosters between SQLite and Google Sheets.

## 2. Voice & Audio
- Library: `PyNaCl`, `opus` (`libopus.so.0`), `davey` (Discord E2EE voice protocol).
- Pre-rendered clips: `audio/audioNumber_*.mp3` for countdown synchronization.
- Text-to-speech: `gTTS` generates temporary voice clips for dynamic callouts.

## 3. Code Redemption Flow (`utils/redeem_code.py`)
- Automated redemption against game publisher web API endpoints.
- Rate-limiting: Implement worker semaphore and delay backoff to avoid HTTP 429 rate limits or IP bans.

