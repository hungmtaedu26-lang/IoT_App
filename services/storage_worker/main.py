import json
import io
import time
from datetime import datetime
from minio import Minio
from minio.error import S3Error
from kafka import KafkaConsumer

# --- CẤU HÌNH ---
# Các giá trị này khớp với tên service trong docker-compose.yml
KAFKA_BROKER = 'kafka:29092'
KAFKA_TOPIC = 'raw_sensor_data'
MINIO_ENDPOINT = 'minio:9000'
MINIO_ACCESS_KEY = 'minioadmin'
MINIO_SECRET_KEY = 'minioadmin'
MINIO_BUCKET_NAME = 'iot-raw-data'

def connect_minio_with_retry():
    """Hàm kết nối tới MinIO, có cơ chế thử lại nếu thất bại."""
    while True:
        try:
            client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=False
            )
            # Kiểm tra xem bucket có tồn tại không, nếu không thì tạo mới
            if not client.bucket_exists(MINIO_BUCKET_NAME):
                client.make_bucket(MINIO_BUCKET_NAME)
                print(f"Da tao bucket MinIO: '{MINIO_BUCKET_NAME}'")
            print("Da ket noi toi MinIO va bucket san sang!")
            return client
        except Exception as e:
            print(f"Khong the ket noi toi MinIO, thu lai sau 5 giay... Loi: {e}")
            time.sleep(5)

def create_kafka_consumer():
    """Tạo Kafka consumer, có cơ chế thử lại nếu thất bại."""
    while True:
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BROKER,
                auto_offset_reset='earliest',
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                group_id='storage-writer-group'
            )
            print("Da ket noi toi Kafka va san sang nhan tin nhan!")
            return consumer
        except Exception as e:
            print(f"Khong the ket noi toi Kafka, thu lai sau 5 giay... Loi: {e}")
            time.sleep(5)

def main():
    print("--- Khoi dong Storage Worker ---")
    
    # === PHẦN BỊ THIẾU TRƯỚC ĐÂY ===
    # 1. Khởi tạo kết nối tới MinIO
    minio_client = connect_minio_with_retry()
    # 2. Khởi tạo Kafka consumer
    consumer = create_kafka_consumer()
    # ================================

    print("Dang cho tin nhan tu Kafka de luu vao MinIO...")
    for message in consumer:
        data = message.value
        print(f"Nhan du lieu de luu vao MinIO: {data}")
        
        try:
            # Lấy địa chỉ MAC để làm tên thư mục, nếu không có thì dùng tên mặc định
            mac = data.get('mac', 'unknown-mac')
            
            # Tạo tên file duy nhất dựa trên thời gian
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
            object_name = f"{mac}/{timestamp}.json"
            
            # Chuyển dictionary Python thành dữ liệu dạng bytes để tải lên
            json_bytes = json.dumps(data).encode('utf-8')
            
            # Tải file lên MinIO
            minio_client.put_object(
                MINIO_BUCKET_NAME, 
                object_name,
                data=io.BytesIO(json_bytes), 
                length=len(json_bytes),
                content_type='application/json'
            )
            print(f"    -> Da luu vao MinIO: {object_name}")

        except S3Error as e:
            print(f"    -> ERROR: Loi khi luu vao MinIO: {e}")
        except Exception as e:
            print(f"    -> ERROR: Loi khong xac dinh: {e}")

if __name__ == "__main__":
    main()