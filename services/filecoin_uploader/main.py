import json
import logging
import os
import time
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Dict, Optional, Tuple

import mysql.connector
import requests
from mysql.connector import Error
from watchfiles import Change, watch

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("filecoin_uploader")

MYSQL_HOST = os.getenv("MYSQL_HOST", "mariadb")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "iot_data")
MYSQL_USER = os.getenv("MYSQL_USER", "myuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "mypassword")

TRANSCRIPTS_DIR = Path(os.getenv("TRANSCRIPTS_DIR", "/app/data/transcripts"))
FILECOIN_DIR = Path(os.getenv("FILECOIN_DIR", "/app/data/filecoin"))
LIGHTHOUSE_API_KEY = os.getenv("LIGHTHOUSE_API_KEY")
LIGHTHOUSE_UPLOAD_URL = os.getenv(
    "LIGHTHOUSE_UPLOAD_URL",
    "https://upload.lighthouse.storage/api/v0/add",
)


def connect_db_with_retry() -> mysql.connector.MySQLConnection:
    while True:
        try:
            conn = mysql.connector.connect(
                host=MYSQL_HOST,
                database=MYSQL_DATABASE,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
            )
            if conn.is_connected():
                logger.info("Connected to MariaDB at %s", MYSQL_HOST)
                return conn
        except Error as exc:
            logger.error("Cannot connect to MariaDB (%s). Retrying in 5s...", exc)
        time.sleep(5)


def ensure_directories() -> None:
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    FILECOIN_DIR.mkdir(parents=True, exist_ok=True)


def ensure_daily_transcripts_table(conn: mysql.connector.MySQLConnection) -> None:
    query = """
    CREATE TABLE IF NOT EXISTS daily_transcripts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        mac_address VARCHAR(64) NOT NULL,
        date DATE NOT NULL,
        trace_id VARCHAR(128) NOT NULL,
        transcript_path VARCHAR(255) NOT NULL,
        filecoin_cid VARCHAR(128),
        filecoin_deal_id VARCHAR(128),
        filecoin_provider VARCHAR(32),
        status ENUM('pending','uploading','uploaded','failed') DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uniq_mac_date (mac_address, date)
    )
    """
    cursor = conn.cursor()
    try:
        cursor.execute(query)
        conn.commit()
    finally:
        cursor.close()


def isoformat_now() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_record_exists(
    conn: mysql.connector.MySQLConnection,
    mac: str,
    date_value: date,
    trace_id: str,
    transcript_path: Path,
) -> None:
    query = """
    INSERT INTO daily_transcripts (mac_address, date, trace_id, transcript_path, status)
    VALUES (%s, %s, %s, %s, 'pending')
    ON DUPLICATE KEY UPDATE
        trace_id = VALUES(trace_id),
        transcript_path = VALUES(transcript_path),
        updated_at = CURRENT_TIMESTAMP
    """
    cursor = conn.cursor()
    try:
        cursor.execute(query, (mac, date_value, trace_id, str(transcript_path)))
        conn.commit()
    finally:
        cursor.close()


def fetch_transcript_record(
    conn: mysql.connector.MySQLConnection,
    mac: str,
    date_value: date,
) -> Optional[Dict]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT status, filecoin_cid, filecoin_deal_id, filecoin_provider
            FROM daily_transcripts
            WHERE mac_address = %s AND date = %s
            """,
            (mac, date_value),
        )
        return cursor.fetchone()
    finally:
        cursor.close()


def resolve_metadata_path(
    provider: Optional[str],
    cid: Optional[str],
    deal_id: Optional[str],
) -> Optional[Path]:
    if provider == "lighthouse" and cid:
        return FILECOIN_DIR / f"lighthouse_{cid}.json"
    if provider == "mock" and deal_id:
        return FILECOIN_DIR / f"deal_{deal_id}.json"
    return None


def update_status(
    conn: mysql.connector.MySQLConnection,
    mac: str,
    date_value: date,
    status: str,
    *,
    cid: Optional[str] = None,
    deal_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> None:
    cursor = conn.cursor()
    try:
        query = """
        UPDATE daily_transcripts
        SET status = %s,
            filecoin_cid = %s,
            filecoin_deal_id = %s,
            filecoin_provider = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE mac_address = %s
          AND date = %s
        """
        cursor.execute(query, (status, cid, deal_id, provider, mac, date_value))
        conn.commit()
    finally:
        cursor.close()


def poseidon_like_hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _mock_deal(content: bytes) -> Tuple[str, str]:
    prefix = content[:32] or content
    suffix = content[-32:] or content
    cid = poseidon_like_hash(prefix)
    deal_num = int(poseidon_like_hash(suffix), 16) % (10**12)
    deal_id = str(deal_num).zfill(12)
    return deal_id, cid


def _lighthouse_upload(transcript_path: Path) -> Dict:
    with open(transcript_path, "rb") as f:
        files = {"file": (transcript_path.name, f, "application/json")}
        headers = {"Authorization": f"Bearer {LIGHTHOUSE_API_KEY}"}
        response = requests.post(
            LIGHTHOUSE_UPLOAD_URL,
            headers=headers,
            files=files,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()


def _extract_cid_from_response(response: Dict, fallback_hash: str) -> str:
    data = response.get("data") or {}
    for key in ("Hash", "cid", "CID", "IpfsHash"):
        if key in data and data[key]:
            return str(data[key])
    for key in ("Hash", "cid", "CID"):
        if key in response and response[key]:
            return str(response[key])
    return fallback_hash


def _extract_deal_from_response(response: Dict) -> Optional[str]:
    for key in ("dealStatus", "dealInfo", "deal_status"):
        if key not in response or not response[key]:
            continue
        value = response[key]
        if isinstance(value, list):
            for item in value:
                deal = _extract_deal_id_from_obj(item)
                if deal:
                    return deal
        elif isinstance(value, dict):
            deal = _extract_deal_id_from_obj(value)
            if deal:
                return deal
    return None


def _extract_deal_id_from_obj(obj: Dict) -> Optional[str]:
    for key in ("dealId", "deal_id", "deal", "id"):
        if key in obj and obj[key]:
            return str(obj[key])
    return None


def write_metadata_file(filename: str, payload: Dict) -> Path:
    path = FILECOIN_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def handle_upload(
    transcript_path: Path,
    transcript: Dict,
    content_bytes: bytes,
) -> Tuple[str, str, str]:
    trace_id = transcript["trace_id"]
    mac = transcript["mac"]
    date_str = transcript["date"]
    hash_transcript = poseidon_like_hash(content_bytes)
    size_bytes = len(content_bytes)

    if not LIGHTHOUSE_API_KEY:
        deal_id, cid = _mock_deal(content_bytes)
        metadata = {
            "provider": "mock",
            "cid": cid,
            "deal_id": deal_id,
            "transcript": transcript_path.name,
            "mac": mac,
            "date": date_str,
            "trace_id": trace_id,
            "hash_transcript": hash_transcript,
            "size_bytes": size_bytes,
            "status": "submitted",
            "generated_at": isoformat_now(),
        }
        write_metadata_file(f"deal_{deal_id}.json", metadata)
        return "mock", cid, deal_id

    response = _lighthouse_upload(transcript_path)
    cid = _extract_cid_from_response(response, hash_transcript)
    deal_id = _extract_deal_from_response(response)
    metadata = {
        "provider": "lighthouse",
        "cid": cid,
        "deal_id": deal_id,
        "transcript": transcript_path.name,
        "mac": mac,
        "date": date_str,
        "trace_id": trace_id,
        "hash_transcript": hash_transcript,
        "size_bytes": size_bytes,
        "response": response,
        "uploaded_at": isoformat_now(),
    }
    write_metadata_file(f"lighthouse_{cid}.json", metadata)
    return "lighthouse", cid, deal_id or ""


def process_transcript_file(
    conn: mysql.connector.MySQLConnection,
    path: Path,
    processed_hashes: Dict[str, str],
) -> None:
    if not path.exists() or path.suffix.lower() != ".json":
        return
    try:
        content_bytes = path.read_bytes()
        transcript = json.loads(content_bytes.decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to read transcript %s: %s", path, exc)
        return

    trace_id = transcript.get("trace_id")
    mac = transcript.get("mac")
    date_str = transcript.get("date")
    if not trace_id or not mac or not date_str:
        logger.warning("Transcript %s missing trace_id/mac/date. Skipping.", path)
        return

    try:
        date_value = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        logger.warning("Transcript %s has invalid date: %s", path, date_str)
        return

    content_hash = poseidon_like_hash(content_bytes)
    if processed_hashes.get(trace_id) == content_hash:
        return

    existing_record = fetch_transcript_record(conn, mac, date_value)
    if existing_record and existing_record.get("status") == "uploaded":
        metadata_path = resolve_metadata_path(
            existing_record.get("filecoin_provider"),
            existing_record.get("filecoin_cid"),
            existing_record.get("filecoin_deal_id"),
        )
        existing_hash = None
        if metadata_path and metadata_path.exists():
            try:
                with open(metadata_path, "r", encoding="utf-8") as meta_fp:
                    metadata = json.load(meta_fp)
                    existing_hash = metadata.get("hash_transcript")
            except Exception:
                existing_hash = None
        if existing_hash == content_hash:
            processed_hashes[trace_id] = content_hash
            logger.debug("Transcript %s already uploaded and unchanged, skipping.", trace_id)
            return

    ensure_record_exists(conn, mac, date_value, trace_id, path)
    update_status(conn, mac, date_value, "uploading")

    try:
        provider, cid, deal_id = handle_upload(path, transcript, content_bytes)
        update_status(conn, mac, date_value, "uploaded", cid=cid, deal_id=deal_id, provider=provider)
        processed_hashes[trace_id] = content_hash
        logger.info(
            "Uploaded transcript %s via %s (cid=%s, deal_id=%s)",
            trace_id,
            provider,
            cid,
            deal_id,
        )
    except requests.RequestException as exc:
        logger.error("Lighthouse upload failed for %s: %s", trace_id, exc)
        update_status(conn, mac, date_value, "failed")
        processed_hashes.pop(trace_id, None)
    except Exception as exc:
        logger.exception("Unexpected error while uploading %s: %s", trace_id, exc)
        update_status(conn, mac, date_value, "failed")
        processed_hashes.pop(trace_id, None)


def initial_scan(
    conn: mysql.connector.MySQLConnection,
    processed_hashes: Dict[str, str],
) -> None:
    for path in sorted(TRANSCRIPTS_DIR.glob("*.json")):
        process_transcript_file(conn, path, processed_hashes)


def monitor() -> None:
    ensure_directories()
    conn = connect_db_with_retry()
    ensure_daily_transcripts_table(conn)

    processed_hashes: Dict[str, str] = {}
    initial_scan(conn, processed_hashes)

    try:
        for changes in watch(TRANSCRIPTS_DIR):
            for change_type, path_str in changes:
                if change_type == Change.deleted:
                    continue
                path = Path(path_str)
                if path.suffix.lower() != ".json":
                    continue
                if not conn.is_connected():
                    conn.close()
                    conn = connect_db_with_retry()
                    ensure_daily_transcripts_table(conn)
                process_transcript_file(conn, path, processed_hashes)
    except KeyboardInterrupt:
        logger.info("Filecoin uploader stopped.")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    monitor()
