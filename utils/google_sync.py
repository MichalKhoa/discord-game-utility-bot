import os
import json
import sqlite3
import datetime
from typing import Optional, List, Dict, Any

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

DEFAULT_DRIVE_FOLDER_ID = "1_OU5Dt7bhczgaJ8UOndF6B4qIGxTGLJ5"
DEFAULT_SHEET_ID = "1OST7SFBUbdnpV2Gun0-Xc49dCF1W1c3oE9C5wAwjC7c"

def get_drive_folder_id() -> str:
    return os.getenv("GOOGLE_DRIVE_FOLDER_ID", DEFAULT_DRIVE_FOLDER_ID).strip()

def get_sheet_id() -> str:
    raw_id = os.getenv("GOOGLE_SHEET_ID", DEFAULT_SHEET_ID).strip()
    if "/d/" in raw_id:
        raw_id = raw_id.split("/d/")[1].split("/")[0]
    elif "/" in raw_id:
        raw_id = raw_id.split("/")[0]
    return raw_id

def get_google_credentials():
    """Loads Google Service Account credentials from environment or local JSON file."""
    try:
        from google.oauth2 import service_account
    except ImportError:
        return None

    env_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if env_json:
        if env_json.startswith("{"):
            try:
                info = json.loads(env_json)
                return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            except Exception as e:
                print(f"[GoogleSync] Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
        elif os.path.exists(env_json):
            try:
                return service_account.Credentials.from_service_account_file(env_json, scopes=SCOPES)
            except Exception as e:
                print(f"[GoogleSync] Failed to read credentials from {env_json}: {e}")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate_paths = [
        os.path.join(base_dir, "service-account.json"),
        os.path.join(base_dir, "utils", "service-account.json"),
        os.path.join(base_dir, "data", "service-account.json"),
        "/app/service-account.json",
        "service-account.json"
    ]

    for path in candidate_paths:
        if os.path.exists(path):
            try:
                return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
            except Exception as e:
                print(f"[GoogleSync] Failed loading credentials from {path}: {e}")

    return None

def create_local_backup(db_path: str, backup_dir: Optional[str] = None) -> str:
    """Creates a point-in-time snapshot of the SQLite database using the Online Backup API."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")

    if backup_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backup_dir = os.path.join(base_dir, "data", "backups")

    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_path = os.path.join(backup_dir, f"players_{timestamp}.db")

    src = sqlite3.connect(db_path)
    dest = sqlite3.connect(dest_path)
    try:
        src.backup(dest)
    finally:
        src.close()
        dest.close()

    return dest_path

def cleanup_local_backups(backup_dir: Optional[str] = None, keep_last_n: int = 7) -> int:
    """Removes older local backups keeping only the most recent keep_last_n files."""
    if backup_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backup_dir = os.path.join(base_dir, "data", "backups")

    if not os.path.exists(backup_dir):
        return 0

    files = [
        os.path.join(backup_dir, f)
        for f in os.listdir(backup_dir)
        if f.startswith("players_") and f.endswith(".db")
    ]
    files.sort(key=os.path.getmtime, reverse=True)

    deleted_count = 0
    for old_file in files[keep_last_n:]:
        try:
            os.remove(old_file)
            deleted_count += 1
        except Exception:
            pass
    return deleted_count

def upload_backup_to_drive(
    file_path: str,
    folder_id: Optional[str] = None,
    keep_last_n: int = 7
) -> Dict[str, Any]:
    """Uploads a backup file to Google Drive and purges older backups in the target folder."""
    creds = get_google_credentials()
    if not creds:
        raise ValueError("Google Service Account credentials not configured or invalid.")

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    folder_id = (folder_id or get_drive_folder_id()).strip()
    service = build('drive', 'v3', credentials=creds, cache_discovery=False)

    file_name = os.path.basename(file_path)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id] if folder_id else []
    }
    media = MediaFileUpload(file_path, mimetype='application/x-sqlite3', resumable=True)

    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name, size, webViewLink'
    ).execute()

    deleted_drive_count = 0
    if folder_id:
        try:
            query = f"'{folder_id}' in parents and name contains 'players_' and trashed = false"
            results = service.files().list(
                q=query,
                orderBy='createdTime desc',
                fields='files(id, name, createdTime)'
            ).execute()
            drive_files = results.get('files', [])

            if len(drive_files) > keep_last_n:
                for old in drive_files[keep_last_n:]:
                    try:
                        service.files().delete(fileId=old['id']).execute()
                        deleted_drive_count += 1
                    except Exception:
                        pass
        except Exception as e:
            print(f"[GoogleSync] Drive cleanup error: {e}")

    return {
        "file_id": uploaded_file.get('id'),
        "file_name": uploaded_file.get('name'),
        "size_bytes": uploaded_file.get('size'),
        "drive_link": uploaded_file.get('webViewLink'),
        "drive_deleted_count": deleted_drive_count
    }

def export_players_to_sheet(
    players: List[Dict[str, Any]],
    sheet_id: Optional[str] = None
) -> Dict[str, Any]:
    """Exports player records to a Google Sheet."""
    creds = get_google_credentials()
    if not creds:
        raise ValueError("Google Service Account credentials not configured or invalid.")

    try:
        import gspread
    except ImportError:
        raise ImportError("Python package 'gspread' is not installed. Please install requirements or rebuild Docker container.")

    target_sheet_id = (sheet_id or get_sheet_id()).strip()
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(target_sheet_id)

    try:
        worksheet = spreadsheet.worksheet("Players")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.sheet1

    headers = [
        "FID",
        "KID",
        "Name",
        "Alliance",
        "Discord ID",
        "Status",
        "Warning Count",
        "Warning Reason",
        "Last Updated"
    ]

    rows = []
    for p in players:
        rows.append([
            str(p.get("fid", "")),
            str(p.get("kid", "278")),
            str(p.get("name", "") or ""),
            str(p.get("alliance", "") or ""),
            str(p.get("discord_id", "") or "") if p.get("discord_id") else "",
            str(p.get("status", "ACTIVE")),
            int(p.get("warning_count", 0)),
            str(p.get("warning_reason", "") or "") if p.get("warning_reason") else "",
            str(p.get("updated_at", "") or "")
        ])

    worksheet.clear()
    worksheet.update(values=[headers] + rows)

    return {
        "total_exported": len(players),
        "spreadsheet_title": spreadsheet.title,
        "spreadsheet_url": spreadsheet.url
    }

def import_players_from_sheet(sheet_id: Optional[str] = None) -> Dict[str, Any]:
    """Reads players from Google Sheet and validates each row."""
    creds = get_google_credentials()
    if not creds:
        raise ValueError("Google Service Account credentials not configured or invalid.")

    try:
        import gspread
    except ImportError:
        raise ImportError("Python package 'gspread' is not installed. Please install requirements or rebuild Docker container.")

    target_sheet_id = (sheet_id or get_sheet_id()).strip()
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(target_sheet_id)

    try:
        worksheet = spreadsheet.worksheet("Players")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.sheet1

    all_values = worksheet.get_all_values()
    if not all_values:
        return {"valid_players": [], "skipped_rows": [], "total_read": 0}

    headers = [h.strip().lower().replace(" ", "_") for h in all_values[0]]
    raw_rows = all_values[1:]

    valid_players: List[Dict[str, Any]] = []
    skipped_rows: List[Dict[str, Any]] = []

    def get_val(row_dict: Dict[str, str], *keys: str) -> str:
        for k in keys:
            if k in row_dict:
                return row_dict[k].strip()
        return ""

    for index, row in enumerate(raw_rows, start=2):
        if not any(cell.strip() for cell in row):
            continue

        row_dict = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}

        fid = get_val(row_dict, "fid", "player_id", "id")
        if not fid:
            skipped_rows.append({"row": index, "reason": "Missing FID"})
            continue

        if not fid.isdigit():
            skipped_rows.append({"row": index, "reason": f"FID '{fid}' must contain numbers only"})
            continue

        kid = get_val(row_dict, "kid", "kingdom", "kingdom_id") or "278"
        name = get_val(row_dict, "name", "ign", "in-game_name")
        alliance = get_val(row_dict, "alliance", "tag", "alliance_tag")
        
        discord_id_raw = get_val(row_dict, "discord_id", "discord", "user_id")
        discord_id = int(discord_id_raw) if discord_id_raw.isdigit() else None

        status_raw = get_val(row_dict, "status").upper()
        status = status_raw if status_raw in ["ACTIVE", "FLAGGED", "DISABLED"] else "ACTIVE"

        warning_raw = get_val(row_dict, "warning_count", "warnings", "strikes")
        warning_count = int(warning_raw) if warning_raw.isdigit() else 0

        warning_reason = get_val(row_dict, "warning_reason", "reason") or None

        valid_players.append({
            "fid": fid,
            "kid": kid,
            "name": name,
            "alliance": alliance,
            "discord_id": discord_id,
            "status": status,
            "warning_count": warning_count,
            "warning_reason": warning_reason
        })

    return {
        "valid_players": valid_players,
        "skipped_rows": skipped_rows,
        "total_read": len(raw_rows),
        "spreadsheet_title": spreadsheet.title,
        "spreadsheet_url": spreadsheet.url
    }
