import serial
import json
import re
import time
from kafka import KafkaProducer

# --- CẤU HÌNH ---
SERIAL_PORT = 'COM5' # Đổi cổng COM của bạn ở đây
BAUD_RATE = 115200
KAFKA_BROKER = 'localhost:9092'
KAFKA_TOPIC = 'raw_sensor_data'

def create_kafka_producer():
    """Tạo Kafka producer với cơ chế retry."""
    while True:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            print("Da ket noi thanh cong toi Kafka Broker!")
            return producer
        except Exception as e:
            print(f"Khong the ket noi toi Kafka, thu lai sau 5 giay... Loi: {e}")
            time.sleep(5)

def main():
    print("--- Khoi dong Ingestion Service ---")
    producer = create_kafka_producer()

    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as ser:
            print(f"Dang lang nghe du lieu tren cong {SERIAL_PORT}...")
            current_json_data = None
            
            while True:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line: continue

                if line.startswith("Nhan duoc goi tin JSON:"):
                    try:
                        json_string = line.split(":", 1)[1].strip()
                        current_json_data = json.loads(json_string)[0]
                    except Exception:
                        current_json_data = None
                
                elif line.startswith("Voi cuong do tin hieu (RSSI):") and current_json_data:
                    rssi_match = re.search(r'(-?\d+)', line)
                    if rssi_match:
                        rssi = int(rssi_match.group(1))
                        
                        # Gộp RSSI vào gói tin JSON
                        current_json_data['rssi'] = rssi
                        
                        print(f"--> Da gop goi tin: {current_json_data}")
                        
                        # Đẩy gói tin hoàn chỉnh vào Kafka
                        producer.send(KAFKA_TOPIC, current_json_data)
                        producer.flush() # Đảm bảo tin nhắn được gửi đi
                        print(f"    -> Da day vao Kafka topic '{KAFKA_TOPIC}'")

                    current_json_data = None # Reset để chờ gói tin mới

    except serial.SerialException as e:
        print(f"FATAL ERROR: Khong the mo cong Serial '{SERIAL_PORT}'.")
    except KeyboardInterrupt:
        print("\nDung chuong trinh.")
    finally:
        if producer:
            producer.close()
        print("Ingestion Service da dung.")

if __name__ == "__main__":
    main()