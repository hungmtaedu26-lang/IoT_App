import os
import requests
from pathlib import Path

# Hardcode the path to the encrypted file we found
FILE_PATH = Path(r"d:\K36A\KI3\IOT\iot_realtime_dashboard\data\filecoin\901506D736D4_2025-11-18_encrypted.bin")
LIGHTHOUSE_UPLOAD_URL = "https://upload.lighthouse.storage/api/v0/add"

# Try to read API Key from env var or .env file (manual parsing since we can't load dotenv lib easily if not installed)
api_key = os.getenv("LIGHTHOUSE_API_KEY")
if not api_key:
    try:
        with open(r"d:\K36A\KI3\IOT\iot_realtime_dashboard\.env", "r") as f:
            for line in f:
                if line.startswith("LIGHTHOUSE_API_KEY="):
                    api_key = line.strip().split("=", 1)[1]
                    break
    except Exception:
        pass

print(f"API Key found: {'Yes' if api_key else 'No'}")
if api_key:
    print(f"API Key (first 5 chars): {api_key[:5]}...")

if not FILE_PATH.exists():
    print(f"File not found: {FILE_PATH}")
    exit(1)

print(f"Attempting to upload {FILE_PATH}...")

try:
    with open(FILE_PATH, "rb") as f:
        files = {"file": (FILE_PATH.name, f, "application/octet-stream")}
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.post(
            LIGHTHOUSE_UPLOAD_URL,
            headers=headers,
            files=files,
            timeout=60,
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        response.raise_for_status()
        print("Upload SUCCESS!")
except Exception as e:
    print(f"Upload FAILED: {e}")
