import datetime
import io
import os
from time import process_time, perf_counter

import requests
import hashlib
import json
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_ACCOUNT_FILE = os.path.join(PROJECT_ROOT, 'service-account.json')
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
DOC_ID = '13qeSSMJH3S4ArPj8B3SJ31UajjS5wIqmt8MYYTvBWhE' #playerID.txt on the GDisk

def get_drive_service():
    # Authenticate using the service account key file
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    return build('drive', 'v3', credentials=creds)

def download_google_doc(file_id: str, output_filename: str):
    service = get_drive_service()

    # Export as plain text
    request = service.files().export_media(fileId=file_id, mimeType='text/plain')

    with io.FileIO(output_filename, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}%.")


def update_file_if_needed(file_id, local_destination):
    service = get_drive_service()

    # 1. Fetch metadata (modifiedTime instead of md5)
    remote_file = service.files().get(fileId=file_id, fields='modifiedTime, name').execute()
    remote_time_str = remote_file.get('modifiedTime')  # Format: 2023-10-27T10:00:00.000Z

    # 2. Check if local file exists and calculate its MD5
    needs_update = True
    # Convert Google Drive ISO 8601 string to a timestamp safely (handles any sub-second length)
    remote_time = datetime.datetime.fromisoformat(remote_time_str.replace('Z', '+00:00')).timestamp()

    if os.path.exists(local_destination):
        local_time = os.path.getmtime(local_destination)
        if local_time >= remote_time:
            needs_update = False

    # 3. Download only if necessary
    if needs_update:
        download_google_doc(file_id, local_destination)
        print("File updated.")
    else:
        print("File up to date.")


# Constants from the original script
WOS_ENCRYPT_KEY = "mN4!pQs6JrYwV9"
BASE_URL = "https://kingshot-giftcode.centurygame.com/api"

RESULT_MESSAGES = {
    "SUCCESS": "Successfully redeemed",
    "RECEIVED": "Already redeemed",
    "SAME TYPE EXCHANGE": "Successfully redeemed (same type)",
    "TIME ERROR": "Code has expired",
    "TIMEOUT RETRY": "Server requested retry",
    "USED": "Claim limit reached, unable to claim",
}

def send_signed_post(endpoint, data):
    """
    Prepares, signs, and sends a POST request to the Kingshot API.
    """
    # 1. Add the required millisecond timestamp
    data["time"] = int(time.time() * 1000)

    # 2. Generate the Sign (Security Hash)
    # Sort keys alphabetically as required by the API
    sorted_keys = sorted(data.keys())

    # Create the string for hashing: key1=val1&key2=val2...
    encoded_str = "&".join([
        f"{k}={json.dumps(data[k]) if isinstance(data[k], dict) else data[k]}"
        for k in sorted_keys
    ])

    # Append the secret key and MD5 hash it
    sign_source = f"{encoded_str}{WOS_ENCRYPT_KEY}"
    signature = hashlib.md5(sign_source.encode()).hexdigest()

    # Add signature to the final payload
    data["sign"] = signature

    # 3. Execute the Request
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

'''
--- EXAMPLE USAGE ---

Step 1: "Login" to validate the Player ID (FID)
player_info = send_signed_post("player", {"fid": "49089798"})
print(f"Player Check: {player_info}")

Step 2: Redeem the Gift Code (CDK)
if player_info.get("code") == 0:
    redeem_result = send_signed_post("gift_code", {
        "fid": "49089798",
        "cdk": "RAMADAN"
    })
    print(f"Redeem Result: {redeem_result}")
'''

def redeem_for_one(playerId, giftCode):
    for i in range(2):
        time.sleep(i+1)
        redeem_result = send_signed_post(
            "gift_code",
            {"fid": f"{playerId}",
             "cdk": f"{giftCode}"
             }
        )
        if redeem_result and redeem_result.get('msg', '').replace('.', '') in ["SUCCESS", "RECEIVED"]:
            return redeem_result
    return None


def redeem_for_all(giftCode: str, file_path="playerIDs.txt"):
    player_count = 0
    start_time = perf_counter()
    start_time_CPU = time.process_time()

    # update_file_if_needed(DOC_ID, file_path)

    if not os.path.exists(file_path):
        return f"File {file_path} not found."

    with open(file_path, "r", encoding="utf-8-sig") as f:
        for line in f.readlines():
            line = line.strip()
            if not line or line.startswith('#'):
                if line.startswith('#'):
                    print(line)
                continue
            # print(f"First char ID: {ord(line[0])}")
            player = line.split(" ")
            fid = player[0]
            player_info = send_signed_post("player", {"fid": fid})

            if player_info.get("code") == 0:
                player_count += 1
                # print(player_info.get("data").get("nickname"))

                redeem_result = send_signed_post(
                    "gift_code",
                    {"fid": fid,
                          "cdk": giftCode
                         }
                )
                msg = redeem_result.get('msg', '').replace('.', '')
                if msg == "TIME ERROR":
                    return (f"Giftcode {giftCode} is expired")
                elif msg == "TIMEOUT RETRY":
                    print("Retrying...")
                    redeem_result = redeem_for_one(fid, giftCode)
                    if (redeem_result == None):
                        print(f"Failed to redeem player: {fid}")
                        msg = "Failed" # or some indicator
                    else:
                        msg = redeem_result.get('msg', '').replace('.', '')

                result_message = RESULT_MESSAGES.get(msg, msg)
                nickname = player_info.get("data", {}).get("nickname", "Unknown")
                print(f"Player: {nickname} --> {result_message}")
            else:
                print(f"Player {fid} is invalid. Check the ID again.")
                continue

            time.sleep(1)

    end_time_CPU = time.process_time()
    end_time = perf_counter()
    result_time_CPU = end_time_CPU - start_time_CPU
    result_time = end_time - start_time
    print(f"✅ **Process Complete!**\n"
            f"Code {giftCode} redeemed for {player_count} players in {result_time:.2f}s and in {result_time_CPU:.2f}s CPU process time")
    return (f"✅ **Process Complete!**\n"
            f"Code {giftCode} redeemed for {player_count} players in {result_time:.2f}s and in {result_time_CPU:.2f}s CPU process time")
