import json
import os
import time
from datetime import datetime
from typing import List, Tuple

import mysql.connector
from mysql.connector import Error
from kafka import KafkaConsumer
from kafka.errors import KafkaError

# --- CẤU HÌNH (sẽ đọc từ biến môi trường trong Docker) ---
def parse_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(',') if item.strip()]


KAFKA_BROKERS = parse_csv(os.getenv('KAFKA_BROKERS', 'kafka:29092,localhost:9092'))
KAFKA_RAW_TOPIC = os.getenv('KAFKA_RAW_TOPIC', 'raw_sensor_data')
KAFKA_AI_TOPIC = os.getenv('KAFKA_AI_TOPIC', 'ai_predictions')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'iot_data')
MYSQL_USER = os.getenv('MYSQL_USER', 'myuser')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'mypassword')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', '3306'))
MYSQL_LOCAL_PORT = int(os.getenv('MYSQL_LOCAL_PORT', '3300'))
MYSQL_PRIMARY_HOST = os.getenv('MYSQL_HOST', 'mariadb')


def build_db_endpoints() -> List[Tuple[str, int]]:
    endpoints = []
    endpoints.append((MYSQL_PRIMARY_HOST, MYSQL_PORT))

    if MYSQL_PRIMARY_HOST != 'localhost':
        endpoints.append(('localhost', MYSQL_LOCAL_PORT))
    if MYSQL_PRIMARY_HOST != 'mariadb':
        endpoints.append(('mariadb', MYSQL_PORT))

    seen = set()
    unique = []
    for host, port in endpoints:
        key = (host, port)
        if host and key not in seen:
            unique.append((host, port))
            seen.add(key)
    return unique


DB_ENDPOINTS = build_db_endpoints()


def connect_db_with_retry():
    while True:
        for host, port in DB_ENDPOINTS:
            try:
                conn = mysql.connector.connect(
                    host=host,
                    port=port,
                    database=MYSQL_DATABASE,
                    user=MYSQL_USER,
                    password=MYSQL_PASSWORD
                )
                if conn.is_connected():
                    print(f"Da ket noi toi MariaDB tai {host}:{port}!")
                    return conn
            except Error as e:
                print(f"Khong the ket noi toi MariaDB {host}:{port}, thu diem tiep... Loi: {e}")
        print("Tat ca endpoint MariaDB deu that bai. Thu lai sau 5 giay...")
        time.sleep(5)


def ensure_tables(conn):
    """Tạo các bảng nếu chưa tồn tại."""
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
        print("Da dam bao cac bang sensor_readings va ai_predictions ton tai.")
    finally:
        cursor.close()


def create_kafka_consumer():
    while True:
        try:
            consumer = KafkaConsumer(
                KAFKA_RAW_TOPIC,
                KAFKA_AI_TOPIC,
                bootstrap_servers=KAFKA_BROKERS,
                auto_offset_reset='earliest',
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                group_id='db-writer-group'
            )
            print(f"Da ket noi toi Kafka ({KAFKA_BROKERS}), san sang nhan cac topic: {KAFKA_RAW_TOPIC}, {KAFKA_AI_TOPIC}")
            return consumer
        except Exception as e:
            print(f"Khong the ket noi toi Kafka ({KAFKA_BROKERS}), thu lai sau 5 giay... Loi: {e}")
            time.sleep(5)


def parse_timestamp(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.utcnow()
    try:
        if isinstance(value, str) and value.endswith('Z'):
            value = value[:-1] + '+00:00'
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.utcnow()


def store_sensor_reading(conn, data):
    mac = data.get('mac')
    if not mac:
        print("    -> WARNING: Bo qua ban ghi sensor vi khong co MAC.")
        return

    cursor = conn.cursor()
    try:
        query = (
            """
            INSERT INTO sensor_readings 
            (mac_address, ax_g, temp, bpm, spo2, validBPM, validSPO2, finger_detected, rssi) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        )
        values = (
            mac,
            data.get('ax_g'),
            data.get('temp'),
            data.get('bpm'),
            data.get('spo2'),
            data.get('validBPM'),
            data.get('validSPO2'),
            data.get('finger'),
            data.get('rssi')
        )
        cursor.execute(query, values)
        conn.commit()
        print("    -> Da luu sensor_reading vao MariaDB.")
    finally:
        cursor.close()


def store_ai_prediction(conn, payload):
    original = payload.get('original_data') or {}
    mac = original.get('mac')
    if not mac:
        print("    -> WARNING: Bo qua ban ghi AI prediction vi khong co MAC.")
        return

    probability = payload.get('probability')
    if probability is None:
        print("    -> WARNING: Bo qua AI prediction vi khong co truong probability.")
        return

    cursor = conn.cursor()
    try:
        query = (
            """
            INSERT INTO ai_predictions
            (mac_address, probability, prediction, bpm, spo2, temp, ax_g, analyzed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
        )
        analyzed_at = parse_timestamp(payload.get('analyzed_at'))
        values = (
            mac,
            float(probability),
            int(payload.get('prediction', 0)),
            original.get('bpm'),
            original.get('spo2'),
            original.get('temp'),
            original.get('ax_g'),
            analyzed_at
        )
        cursor.execute(query, values)
        conn.commit()
        print("    -> Da luu ai_prediction vao MariaDB.")
    finally:
        cursor.close()


def main():
    print("--- Khoi dong Database Worker ---")

    consumer = create_kafka_consumer()
    db_conn = connect_db_with_retry()
    ensure_tables(db_conn)

    print("Dang cho tin nhan tu Kafka...")
    while True:
        try:
            message_batches = consumer.poll(timeout_ms=1000, max_records=50)
            if not message_batches:
                continue

            for _, messages in message_batches.items():
                for message in messages:
                    data = message.value
                    topic = message.topic

                    try:
                        if topic == KAFKA_RAW_TOPIC:
                            print(f"Nhan du lieu sensor: {data}")
                            store_sensor_reading(db_conn, data)
                        elif topic == KAFKA_AI_TOPIC:
                            print(f"Nhan du lieu AI prediction: {data}")
                            store_ai_prediction(db_conn, data)
                    except Error as e:
                        print(f"    -> ERROR: Loi khi luu vao MariaDB: {e}")
                        db_conn.rollback()
                        if not db_conn.is_connected():
                            db_conn = connect_db_with_retry()
                            ensure_tables(db_conn)
                    except Exception as e:
                        print(f"    -> ERROR: Loi khong xac dinh: {e}")

        except (KafkaError, ValueError) as e:
            print(f"--> WARNING: Mat ket noi Kafka ({e}). Dang khoi tao lai consumer...")
            try:
                consumer.close()
            except Exception:
                pass
            time.sleep(5)
            consumer = create_kafka_consumer()


if __name__ == "__main__":
    main()
