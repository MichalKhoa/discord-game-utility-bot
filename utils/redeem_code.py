import csv
import datetime
import hashlib
import json
import os
import random
import sqlite3
import time
from time import perf_counter, process_time
from typing import Tuple, List, Optional
import requests



def update_file_from_public_url(doc_id: str, local_destination: str) -> bool:
    """
    Downloads the Google Doc as plain text using the public export URL.
    Always overwrites the local file with the latest version.
    Returns True if successful, False otherwise.
    """
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        content = response.text
        
        # Write to local destination
        with open(local_destination, "w", encoding="utf-8") as f:
            f.write(content)
        print("Player IDs file updated successfully from public Google Doc URL.")
        return True
    except Exception as e:
        print(f"⚠️ Failed to download player IDs from Google Doc: {e}")
        return False


BASE_URL = "https://kingshot-giftcode.centurygame.com"
REDEEM_URL = BASE_URL + "/api/gift_code"
ORIGIN = BASE_URL
KS_ENCRYPT_KEY = "mN4!pQs6JrYwV9"
WOS_ENCRYPT_KEY = KS_ENCRYPT_KEY  # Backward compatibility
DEFAULT_KINGDOM = "278"

DELAY = 1.0                 # seconds between player IDs
RETRY_DELAY = 2             # seconds between transport retries
MAX_RETRIES = 3             # transport retries per request
MAX_FID_ATTEMPTS = 3        # redemption attempts per player before giving up
TOO_FREQUENT_SLEEP = 60     # per-FID cooldown after a TOO FREQUENT (40019)
MAX_COOLDOWNS = 3           # cooldowns a single player may take before being given up on
MAX_CONSECUTIVE_FAILURES = 10   # players in a row unable to reach the API before aborting
MAX_KINGDOM_ID = 999999     # kingdom ID ceiling

TRANSPORT_FAILURE = "Redemption request failed"

RESULT_MESSAGES = {
    "SUCCESS": "Successfully redeemed",
    "RECEIVED": "Already redeemed",
    "SAME TYPE EXCHANGE": "Successfully redeemed (same type)",
    "TIME ERROR": "Code has expired",
    "CDK NOT FOUND": "Code not found or incorrect",
    "USED": "Claim limit reached, unable to claim",
    "TIMEOUT RETRY": "Server requested retry",
    "TOO FREQUENT": "Rate limited on this player ID",
    "USER INFO ERROR": "Wrong kingdom for this player ID",
    "ROLE NOT EXIST": "No such player",
    "STOVE_LV ERROR": "Town Center level too low for this code",
    "RECHARGE_MONEY ERROR": "Not enough spending for this code",
    "RECHARGE_MONEY_VIP ERROR": "VIP level too low for this code",
    "SIGN ERROR": "Sign error (request encoding issue)",
    "NOT LOGIN": "Session rejected by the server",
}

FATAL_STATUSES = ("TIME ERROR", "CDK NOT FOUND", "USED")
SUCCESS_STATUSES = ("SUCCESS", "SAME TYPE EXCHANGE")

BROWSER_PROFILES = [
    ('Chrome', list(range(124, 136))),
    ('Brave', list(range(132, 146))),
    ('Edge', list(range(124, 136))),
]

PLATFORMS = [
    ('Windows NT 10.0; Win64; x64', '"Windows"'),
    ('Windows NT 11.0; Win64; x64', '"Windows"'),
    ('Macintosh; Intel Mac OS X 10_15_7', '"macOS"'),
    ('X11; Linux x86_64', '"Linux"'),
]

SESSION = requests.Session()


def get_headers():
    """Randomized browser-like headers with proper user-agent alignment and strict browser header ordering."""
    browser, versions = random.choice(BROWSER_PROFILES)
    version = random.choice(versions)
    platform, sec_platform = random.choice(PLATFORMS)

    if browser == 'Edge':
        sec_ch_ua = f'"Not A(B)rand";v="8", "Chromium";v="{version}", "Microsoft Edge";v="{version}"'
        user_agent = (f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) "
                      f"Chrome/{version}.0.0.0 Safari/537.36 Edg/{version}.0.0.0")
    else:
        sec_ch_ua = f'"Not:A-Brand";v="99", "{browser}";v="{version}", "Chromium";v="{version}"'
        user_agent = (f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) "
                      f"Chrome/{version}.0.0.0 Safari/537.36")

    return {
        'host': 'kingshot-giftcode.centurygame.com',
        'sec-ch-ua': sec_ch_ua,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': sec_platform,
        'upgrade-insecure-requests': '1',
        'user-agent': user_agent,
        'accept': 'application/json, text/plain, */*',
        'origin': ORIGIN,
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'referer': ORIGIN + '/',
        'accept-encoding': 'gzip, deflate, br',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded',
    }


def encode_data(data):
    """Sign the payload with the MD5 hash the API expects."""
    sorted_keys = sorted(data.keys())
    encoded = "&".join(f"{key}={data[key]}" for key in sorted_keys)
    return {"sign": hashlib.md5(f"{encoded}{KS_ENCRYPT_KEY}".encode()).hexdigest(), **data}


def make_request(url, payload, headers=None):
    """POST with transport-level retries; returns response or None."""
    if headers is None:
        headers = get_headers()
    for attempt in range(MAX_RETRIES):
        try:
            response = SESSION.post(url, data=payload, headers=headers, timeout=(10, 30))
            if response.status_code == 200:
                return response
            if response.status_code == 429:
                time.sleep(RETRY_DELAY * (attempt + 1) * 2)
                continue
            if response.status_code in (502, 503, 504):
                time.sleep(RETRY_DELAY * (attempt + 1) * 1.5)
                continue
        except requests.exceptions.RequestException:
            pass

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY * (attempt + 1))

    return None


def classify(data):
    """Map an API response to one of the RESULT_MESSAGES keys."""
    if not isinstance(data, dict):
        return "Invalid response format"
    msg = str(data.get("msg", "Unknown error")).strip('.')
    err_code = data.get("err_code")

    if msg == "SUCCESS":
        return "SUCCESS"
    if msg == "RECEIVED" and err_code == 40008:
        return "RECEIVED"
    if msg == "SAME TYPE EXCHANGE" and err_code == 40011:
        return "SAME TYPE EXCHANGE"
    if msg == "TIME ERROR" and err_code == 40007:
        return "TIME ERROR"
    if msg == "CDK NOT FOUND" and err_code == 40014:
        return "CDK NOT FOUND"
    if msg == "USED" and err_code == 40005:
        return "USED"
    if msg == "TIMEOUT RETRY" and err_code == 40004:
        return "TIMEOUT RETRY"
    if msg == "TOO FREQUENT" and err_code == 40019:
        return "TOO FREQUENT"
    if msg == "USER INFO ERROR" and err_code == 40020:
        return "USER INFO ERROR"
    if err_code == 40001 and "not exist" in msg.lower():
        return "ROLE NOT EXIST"
    if msg == "STOVE_LV ERROR" and err_code == 40006:
        return "STOVE_LV ERROR"
    if msg == "RECHARGE_MONEY ERROR" and err_code == 40017:
        return "RECHARGE_MONEY ERROR"
    if msg == "RECHARGE_MONEY_VIP ERROR" and err_code == 40018:
        return "RECHARGE_MONEY_VIP ERROR"
    if "sign error" in msg.lower():
        return "SIGN ERROR"
    if msg == "NOT LOGIN":
        return "NOT LOGIN"
    return msg


def send_signed_post(endpoint, data):
    """Prepares, signs, and sends a POST request to the Kingshot API."""
    data_copy = {k: str(v) for k, v in data.items()}
    if "time" not in data_copy:
        data_copy["time"] = str(int(time.time()))
    if "kid" not in data_copy or not data_copy["kid"]:
        data_copy["kid"] = DEFAULT_KINGDOM

    payload = encode_data(data_copy)
    url = endpoint if endpoint.startswith("http") else f"{BASE_URL}/api/{endpoint}"
    response = make_request(url, payload)
    if response is None:
        return {"error": TRANSPORT_FAILURE}
    try:
        return response.json()
    except ValueError:
        return {"error": "Invalid JSON response"}


def redeem_once(fid, kid, cdk):
    """One signed redemption POST for `fid` in kingdom `kid`; returns status key."""
    payload = encode_data({
        "fid": str(fid),
        "cdk": str(cdk),
        "kid": str(kid) if kid else DEFAULT_KINGDOM,
        "time": str(int(time.time())),
    })
    response = make_request(REDEEM_URL, payload)
    if response is None:
        return TRANSPORT_FAILURE

    try:
        return classify(response.json())
    except ValueError:
        return "Redemption response invalid JSON"


def redeem_for_one(playerId, giftCode, kingdomId=DEFAULT_KINGDOM):
    """Redeem code for a single player ID with retries."""
    for attempt in range(MAX_FID_ATTEMPTS):
        if attempt > 0:
            time.sleep(RETRY_DELAY * attempt)
        res = send_signed_post("gift_code", {"fid": playerId, "cdk": giftCode, "kid": kingdomId or DEFAULT_KINGDOM})
        if "error" not in res:
            status = classify(res)
            if status not in ("TIMEOUT RETRY", "TOO FREQUENT"):
                return res
    return res


def verify_player(fid: str, kid: str = DEFAULT_KINGDOM) -> Tuple[bool, str]:
    """
    Validates player FID and Kingdom ID using Century Games API.
    Returns (is_valid: bool, message: str).
    """
    res = send_signed_post("gift_code", {
        "fid": str(fid).strip(),
        "kid": str(kid).strip() if kid else DEFAULT_KINGDOM,
        "cdk": "VERIFY_PING"
    })
    if "error" in res:
        return False, f"API Connection Error: {res['error']}"

    err_code = res.get("err_code")
    msg = str(res.get("msg", "")).strip('.')

    # 40014 = CDK NOT FOUND, 40007 = TIME ERROR -> means player & kingdom are valid!
    if err_code in (40014, 40007, 0) or msg in ("CDK NOT FOUND", "TIME ERROR", "SUCCESS"):
        return True, "Player and Kingdom verified"
    elif err_code == 40020 or "USER INFO ERROR" in msg:
        return False, f"Invalid Kingdom ID or Player ID does not belong to Kingdom {kid}"
    elif err_code == 40001 or "not exist" in msg.lower():
        return False, "Player ID does not exist"
    else:
        return False, f"API Response: {msg} ({err_code})"


def flag_player_sync(fid: str, reason: str, db_path: str = "data/players.db", threshold: int = 3):
    """Synchronously flag a player in SQLite DB during redemption batch."""
    if not os.path.exists(db_path):
        return
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT warning_count FROM players WHERE fid = ?", (str(fid).strip(),))
            row = cursor.fetchone()
            if not row:
                return
            new_count = row[0] + 1
            new_status = "FLAGGED"
            if new_count >= threshold or "ROLE NOT EXIST" in reason.upper():
                new_status = "DISABLED"
            cursor.execute(
                "UPDATE players SET warning_count = ?, warning_reason = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE fid = ?",
                (new_count, reason, new_status, str(fid).strip())
            )
            conn.commit()
    except Exception as e:
        print(f"Error flagging player {fid} in DB: {e}")


def unflag_player_sync(fid: str, db_path: str = "data/players.db"):
    """Synchronously reset warnings and set ACTIVE on success in SQLite DB."""
    if not os.path.exists(db_path):
        return
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE players SET warning_count = 0, warning_reason = NULL, status = 'ACTIVE', updated_at = CURRENT_TIMESTAMP WHERE fid = ? AND (warning_count > 0 OR status != 'ACTIVE')",
                (str(fid).strip(),)
            )
            conn.commit()
    except Exception:
        pass


def parse_player_line(line):
    """Extract (fid, kid) from a text or CSV line."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None, None
    parts = [p.strip() for p in line.replace(',', ' ').split() if p.strip()]
    if not parts:
        return None, None
    fid = parts[0]
    kid = parts[1] if len(parts) > 1 and parts[1].isdigit() and int(parts[1]) <= MAX_KINGDOM_ID else None
    return fid, kid


def load_players_from_db(db_path: str = "data/players.db") -> List[Tuple[str, str]]:
    """Loads active (non-disabled) players from SQLite database."""
    if not os.path.exists(db_path):
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fid, kid FROM players WHERE status != 'DISABLED' ORDER BY CAST(fid AS INTEGER)")
            rows = cursor.fetchall()
            return [(str(fid), str(kid or DEFAULT_KINGDOM)) for fid, kid in rows]
    except Exception as e:
        print(f"Error loading players from DB: {e}")
        return []


def load_players(file_path="data/players.db", default_kingdom=DEFAULT_KINGDOM):
    """Load and deduplicate (fid, kid) player pairs from SQLite DB or text/CSV file."""
    # Check if target is SQLite DB
    if file_path.endswith(".db") or os.path.exists("data/players.db"):
        db_target = file_path if file_path.endswith(".db") else "data/players.db"
        if os.path.exists(db_target):
            db_players = load_players_from_db(db_target)
            if db_players:
                return db_players

    if not os.path.exists(file_path):
        return []

    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'gbk']
    lines = []
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                lines = f.readlines()
            break
        except FileNotFoundError:
            raise
        except UnicodeDecodeError:
            continue
        except Exception:
            return []

    raw = []
    for line in lines:
        fid, kid = parse_player_line(line)
        if fid and fid.isdigit():
            raw.append((fid, kid))

    kingdoms = {}
    for fid, kid in raw:
        if kid or fid not in kingdoms:
            kingdoms[fid] = kid or kingdoms.get(fid)

    players = []
    for fid in sorted(kingdoms, key=lambda x: int(x) if x.isdigit() else x):
        kid = kingdoms[fid]
        players.append((fid, kid or default_kingdom or DEFAULT_KINGDOM))

    return players


def make_progress_bar(current: int, total: int, length: int = 15) -> str:
    """Returns a visual unicode progress bar string."""
    if total <= 0:
        return "░" * length
    percent = min(1.0, max(0.0, current / total))
    filled = int(round(length * percent))
    return "█" * filled + "░" * (length - filled)


def redeem_for_all(giftCode: str, file_path="data/players.db", default_kingdom=DEFAULT_KINGDOM, progress_callback=None):
    start_time = perf_counter()
    start_time_CPU = process_time()

    try:
        players = load_players(file_path, default_kingdom)
    except Exception as e:
        return f"Error reading player IDs: {e}"

    if not players:
        return f"No valid player IDs found in {file_path}."

    db_path = file_path if file_path.endswith(".db") else "data/players.db"

    counters = {
        "success": 0,
        "already_redeemed": 0,
        "wrong_kingdom": 0,
        "errors": 0,
        "rate_limited": 0,
        "requests": 0,
    }

    if progress_callback:
        try:
            progress_callback(0, len(players), counters, False, 0.0)
        except Exception:
            pass

    retry_queue = {}
    cooldowns = {}
    processed_fids = set()
    stop_processing = False
    consecutive_failures = 0
    fatal_reason = None

    while len(processed_fids) < len(players) and not stop_processing:
        now = time.time()
        ready = [(fid, kid) for fid, kid in players
                 if fid not in processed_fids and retry_queue.get(fid, 0) <= now]
        cooling = len(players) - len(processed_fids) - len(ready)

        if not ready:
            if not cooling:
                break
            next_retry = min(retry_queue[fid] for fid, _ in players
                             if fid not in processed_fids and fid in retry_queue)
            wait = max(1, min(30, next_retry - now + 1))
            time.sleep(wait)
            continue

        for fid, kid in ready:
            SESSION.cookies.clear()
            SESSION.headers.clear()
            SESSION.headers.update(get_headers())
            status = "Processing error"
            for attempt in range(MAX_FID_ATTEMPTS):
                status = redeem_once(fid, kid, giftCode)
                counters["requests"] += 1

                if status == "TOO FREQUENT":
                    counters["rate_limited"] += 1
                    cooldowns[fid] = cooldowns.get(fid, 0) + 1
                    if cooldowns[fid] <= MAX_COOLDOWNS:
                        retry_queue[fid] = time.time() + TOO_FREQUENT_SLEEP
                        break
                elif status == "TIMEOUT RETRY":
                    if attempt < MAX_FID_ATTEMPTS - 1:
                        time.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                break

            if retry_queue.get(fid, 0) > time.time():
                continue

            processed_fids.add(fid)

            if status in SUCCESS_STATUSES:
                counters["success"] += 1
                unflag_player_sync(fid, db_path)
            elif status == "RECEIVED":
                counters["already_redeemed"] += 1
                unflag_player_sync(fid, db_path)
            elif status in ("USER INFO ERROR", "ROLE NOT EXIST"):
                counters["wrong_kingdom"] += 1
                flag_player_sync(fid, status, db_path)
            elif status in FATAL_STATUSES:
                fatal_reason = RESULT_MESSAGES.get(status, status)
                stop_processing = True
                break
            else:
                counters["errors"] += 1

            if progress_callback:
                try:
                    progress_callback(len(processed_fids), len(players), counters, False, perf_counter() - start_time)
                except Exception:
                    pass

            consecutive_failures = consecutive_failures + 1 if status == TRANSPORT_FAILURE else 0
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                fatal_reason = f"{MAX_CONSECUTIVE_FAILURES} consecutive API connection failures"
                stop_processing = True
                break

            human_delay = max(0.5, random.gauss(DELAY + 0.2, 0.3))
            time.sleep(human_delay)

    end_time_CPU = process_time()
    end_time = perf_counter()
    result_time_CPU = end_time_CPU - start_time_CPU
    result_time = end_time - start_time

    if progress_callback:
        try:
            progress_callback(len(processed_fids), len(players), counters, True, result_time)
        except Exception:
            pass

    if fatal_reason:
        return f"Giftcode {giftCode} stopped: {fatal_reason}"

    return (
        f"✅ **Process Complete!**\n"
        f"Code `{giftCode}` redeemed for {len(processed_fids)} players in {result_time:.2f}s "
        f"(CPU: {result_time_CPU:.2f}s)\n"
        f"• Success: {counters['success']}\n"
        f"• Already redeemed: {counters['already_redeemed']}\n"
        f"• Flagged (Wrong/Moved Kingdom or Role Not Exist): {counters['wrong_kingdom']}\n"
        f"• Rate limited: {counters['rate_limited']}\n"
        f"• Other Errors: {counters['errors']}"
    )
