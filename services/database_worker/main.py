import json
import time
import mysql.connector
from mysql.connector import Error
from kafka import KafkaConsumer

# --- CẤU HÌNH (sẽ đọc từ biến môi trường trong Docker) ---
KAFKA_BROKER = 'kafka:29092' # Tên service trong docker-compose
KAFKA_TOPIC = 'raw_sensor_data'
MYSQL_HOST = 'mariadb'
MYSQL_DATABASE = 'iot_data'
MYSQL_USER = 'myuser'
MYSQL_PASSWORD = 'mypassword'

def connect_db_with_retry():
    while True:
        try:
            conn = mysql.connector.connect(
                host=MYSQL_HOST, database=MYSQL_DATABASE,
                user=MYSQL_USER, password=MYSQL_PASSWORD
            )
            if conn.is_connected():
                print("Da ket noi toi MariaDB!")
                return conn
        except Error as e:
            print(f"Khong the ket noi toi MariaDB, thu lai sau 5 giay... Loi: {e}")
            time.sleep(5)

def main():
    print("--- Khoi dong Database Worker ---")
    
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BROKER,
        auto_offset_reset='earliest', # Bắt đầu đọc từ tin nhắn cũ nhất
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id='db-writer-group' # Định danh nhóm consumer
    )

    db_conn = connect_db_with_retry()

    print("Dang cho tin nhan tu Kafka...")
    for message in consumer:
        data = message.value
        print(f"Nhan du lieu de luu vao DB: {data}")
        
        try:
            cursor = db_conn.cursor()
            query = """
                INSERT INTO sensor_readings 
                (mac_address, ax_g, temp, bpm, spo2, validBPM, validSPO2, finger_detected, rssi) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                data.get('mac'), data.get('ax_g'), data.get('temp'),
                data.get('bpm'), data.get('spo2'), data.get('validBPM'),
                data.get('validSPO2'), data.get('finger'), data.get('rssi')
            )
            cursor.execute(query, values)
            db_conn.commit()
            print("    -> Da luu vao MariaDB thanh cong.")
        except Error as e:
            print(f"    -> ERROR: Loi khi luu vao MariaDB: {e}")
            db_conn.rollback()

if __name__ == "__main__":
    main()