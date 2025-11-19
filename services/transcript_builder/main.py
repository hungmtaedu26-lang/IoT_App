import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Set

import mysql.connector
from mysql.connector import Error

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("transcript_builder")

MYSQL_HOST = os.getenv("MYSQL_HOST", "mariadb")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "iot_data")
MYSQL_USER = os.getenv("MYSQL_USER", "myuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "mypassword")

TRANSCRIPTS_DIR = Path(os.getenv("TRANSCRIPTS_DIR", "/app/data/transcripts"))
LOOP_INTERVAL = int(os.getenv("TRANSCRIPT_LOOP_INTERVAL_SEC", "60"))


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


def ensure_source_tables(conn: mysql.connector.MySQLConnection) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                mac_address VARCHAR(64) NOT NULL,
                ax_g FLOAT,
                temp FLOAT,
                bpm FLOAT,
                spo2 FLOAT,
                validBPM TINYINT(1),
                validSPO2 TINYINT(1),
                finger_detected TINYINT(1),
                rssi INT,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_sensor_mac_time (mac_address, received_at)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_predictions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                mac_address VARCHAR(64) NOT NULL,
                probability FLOAT NOT NULL,
                prediction TINYINT(1) NOT NULL,
                bpm FLOAT,
                spo2 FLOAT,
                temp FLOAT,
                ax_g FLOAT,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_prediction_mac_time (mac_address, analyzed_at)
            )
            """
        )
        conn.commit()
    finally:
        cursor.close()


def isoformat_utc(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_float(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def safe_int(value: Optional[Decimal]) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def fetch_distinct_macs(conn: mysql.connector.MySQLConnection, target_date: date) -> Set[str]:
    macs: Set[str] = set()
    date_str = target_date.isoformat()

    queries = [
        ("SELECT DISTINCT mac_address FROM sensor_readings WHERE DATE(received_at) = %s", date_str),
        ("SELECT DISTINCT mac_address FROM ai_predictions WHERE DATE(analyzed_at) = %s", date_str),
    ]
    for query, param in queries:
        cursor = conn.cursor()
        try:
            cursor.execute(query, (param,))
            for (mac,) in cursor.fetchall():
                if mac:
                    macs.add(mac)
        finally:
            cursor.close()
    return macs


def fetch_sensor_stats(conn: mysql.connector.MySQLConnection, mac: str, target_date: date) -> Dict:
    query = """
    SELECT
        COUNT(*) AS count,
        MIN(received_at) AS first_seen,
        MAX(received_at) AS last_seen,
        MIN(bpm) AS bpm_min,
        MAX(bpm) AS bpm_max,
        AVG(bpm) AS bpm_avg,
        MIN(spo2) AS spo2_min,
        MAX(spo2) AS spo2_max,
        AVG(spo2) AS spo2_avg,
        MIN(temp) AS temp_min,
        MAX(temp) AS temp_max,
        AVG(temp) AS temp_avg,
        MIN(ax_g) AS ax_g_min,
        MAX(ax_g) AS ax_g_max,
        AVG(ax_g) AS ax_g_avg,
        SUM(CASE WHEN validBPM = 1 THEN 1 ELSE 0 END) AS valid_bpm_count,
        SUM(CASE WHEN validSPO2 = 1 THEN 1 ELSE 0 END) AS valid_spo2_count,
        SUM(CASE WHEN finger_detected = 1 THEN 1 ELSE 0 END) AS finger_detected_count
    FROM sensor_readings
    WHERE mac_address = %s
      AND DATE(received_at) = %s
    """
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, (mac, target_date))
        row = cursor.fetchone() or {}
        return row
    finally:
        cursor.close()


def fetch_ai_stats(conn: mysql.connector.MySQLConnection, mac: str, target_date: date) -> Dict:
    query = """
    SELECT
        COUNT(*) AS prediction_count,
        MIN(probability) AS probability_min,
        MAX(probability) AS probability_max,
        AVG(probability) AS probability_avg,
        SUM(CASE WHEN prediction = 1 THEN 1 ELSE 0 END) AS anomaly_count,
        SUM(CASE WHEN prediction = 0 THEN 1 ELSE 0 END) AS normal_count
    FROM ai_predictions
    WHERE mac_address = %s
      AND DATE(analyzed_at) = %s
    """
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, (mac, target_date))
        row = cursor.fetchone() or {}
        return row
    finally:
        cursor.close()


def build_sensor_stats(row: Dict) -> Dict:
    count = safe_int(row.get("count")) or 0
    stats = {
        "count": count,
        "bpm_min": safe_float(row.get("bpm_min")),
        "bpm_max": safe_float(row.get("bpm_max")),
        "bpm_avg": safe_float(row.get("bpm_avg")),
        "spo2_min": safe_float(row.get("spo2_min")),
        "spo2_max": safe_float(row.get("spo2_max")),
        "spo2_avg": safe_float(row.get("spo2_avg")),
        "temp_min": safe_float(row.get("temp_min")),
        "temp_max": safe_float(row.get("temp_max")),
        "temp_avg": safe_float(row.get("temp_avg")),
        "ax_g_min": safe_float(row.get("ax_g_min")),
        "ax_g_max": safe_float(row.get("ax_g_max")),
        "ax_g_avg": safe_float(row.get("ax_g_avg")),
        "valid_bpm_count": safe_int(row.get("valid_bpm_count")) or 0,
        "valid_spo2_count": safe_int(row.get("valid_spo2_count")) or 0,
        "finger_detected_count": safe_int(row.get("finger_detected_count")) or 0,
    }
    return stats


def build_ai_stats(row: Dict) -> Dict:
    prediction_count = safe_int(row.get("prediction_count")) or 0
    anomaly_count = safe_int(row.get("anomaly_count")) or 0
    normal_count = safe_int(row.get("normal_count")) or 0
    anomaly_rate = (anomaly_count / prediction_count) if prediction_count else 0.0
    stats = {
        "prediction_count": prediction_count,
        "probability_min": safe_float(row.get("probability_min")),
        "probability_max": safe_float(row.get("probability_max")),
        "probability_avg": safe_float(row.get("probability_avg")),
        "anomaly_count": anomaly_count,
        "normal_count": normal_count,
        "anomaly_rate": round(anomaly_rate, 6),
    }
    return stats


def upsert_daily_transcript_row(
    conn: mysql.connector.MySQLConnection,
    mac: str,
    target_date: date,
    trace_id: str,
    transcript_path: Path,
) -> None:
    query = """
    INSERT INTO daily_transcripts (mac_address, date, trace_id, transcript_path, status)
    VALUES (%s, %s, %s, %s, 'pending')
    ON DUPLICATE KEY UPDATE
        trace_id = VALUES(trace_id),
        transcript_path = VALUES(transcript_path),
        status = 'pending',
        updated_at = CURRENT_TIMESTAMP
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            query,
            (mac, target_date, trace_id, str(transcript_path)),
        )
        conn.commit()
    finally:
        cursor.close()


def generate_transcript(
    conn: mysql.connector.MySQLConnection,
    mac: str,
    target_date: date,
) -> None:
    sensor_row = fetch_sensor_stats(conn, mac, target_date)
    ai_row = fetch_ai_stats(conn, mac, target_date)

    sensor_count = safe_int(sensor_row.get("count")) or 0
    ai_count = safe_int(ai_row.get("prediction_count")) or 0
    if sensor_count == 0 and ai_count == 0:
        logger.debug("No data for mac=%s on %s, skipping.", mac, target_date)
        return

    trace_id = f"{mac}_{target_date.isoformat()}"
    transcript = {
        "trace_id": trace_id,
        "mac": mac,
        "date": target_date.isoformat(),
        "time_range": {
            "start": isoformat_utc(sensor_row.get("first_seen")),
            "end": isoformat_utc(sensor_row.get("last_seen")),
        },
        "sensor_stats": build_sensor_stats(sensor_row),
        "ai_stats": build_ai_stats(ai_row),
        "meta": {
            "generated_at": isoformat_utc(datetime.utcnow()),
            "source": "mariadb",
            "version": "1.0",
        },
    }

    file_path = TRANSCRIPTS_DIR / f"{trace_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)

    upsert_daily_transcript_row(conn, mac, target_date, trace_id, file_path)
    logger.info("Generated transcript %s", trace_id)


def process_day(conn: mysql.connector.MySQLConnection, target_date: date) -> None:
    macs = fetch_distinct_macs(conn, target_date)
    if not macs:
        logger.debug("No devices with data on %s", target_date)
        return
    for mac in sorted(macs):
        try:
            generate_transcript(conn, mac, target_date)
        except Error as exc:
            logger.error("DB error while generating transcript for %s on %s: %s", mac, target_date, exc)
            raise
        except Exception as exc:
            logger.exception("Unexpected error while generating transcript for %s on %s: %s", mac, target_date, exc)


def main() -> None:
    ensure_directories()
    conn = connect_db_with_retry()
    ensure_source_tables(conn)
    ensure_daily_transcripts_table(conn)

    try:
        while True:
            today = datetime.utcnow().date()
            days: List[date] = [today, today - timedelta(days=1)]
            for target_date in days:
                if not conn.is_connected():
                    conn.close()
                    conn = connect_db_with_retry()
                    ensure_source_tables(conn)
                    ensure_daily_transcripts_table(conn)
                process_day(conn, target_date)
            time.sleep(LOOP_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Transcript builder stopped.")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
