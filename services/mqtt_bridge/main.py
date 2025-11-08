import json
import os
import time
from kafka import KafkaConsumer
import paho.mqtt.client as mqtt

# --- CẤU HÌNH ---
# Đọc thông tin kết nối từ biến môi trường của Docker Compose
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:29092")
KAFKA_TOPICS = os.getenv("KAFKA_TOPICS", "raw_sensor_data,ai_predictions").split(',')
MQTT_BROKER = os.getenv("MQTT_BROKER", "hivemq")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))

def create_kafka_consumer(topics):
    """Tạo Kafka consumer, có cơ chế retry."""
    while True:
        try:
            consumer = KafkaConsumer(
                *topics, # Dấu * để unpack list các topic
                bootstrap_servers=KAFKA_BROKER,
                auto_offset_reset='earliest',
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                group_id='mqtt-bridge-group'
            )
            print(f"Da ket noi toi Kafka va lang nghe cac topic: {topics}")
            return consumer
        except Exception as e:
            print(f"Khong the ket noi toi Kafka, thu lai sau 5 giay... Loi: {e}")
            time.sleep(5)

def create_mqtt_client():
    """Tạo MQTT client, có cơ chế retry."""
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Da ket noi thanh cong toi MQTT Broker!")
        else:
            print(f"Ket noi MQTT that bai, ma loi: {rc}")

    client = mqtt.Client(client_id="mqtt-bridge-service")
    client.on_connect = on_connect
    
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_start() # Bắt đầu luồng riêng để xử lý MQTT
            return client
        except Exception as e:
            print(f"Khong the ket noi toi MQTT Broker, thu lai sau 5 giay... Loi: {e}")
            time.sleep(5)

def get_mac_from_payload(payload):
    """Trích xuất địa chỉ MAC từ các loại payload khác nhau."""
    if 'mac' in payload:
        return payload['mac']
    if 'original_data' in payload and 'mac' in payload['original_data']:
        return payload['original_data']['mac']
    return None

def main():
    print("--- Khoi dong MQTT Bridge ---")
    
    kafka_consumer = create_kafka_consumer(KAFKA_TOPICS)
    mqtt_client = create_mqtt_client()
    
    print("San sang chuyen tiep tin nhan tu Kafka sang MQTT...")
    for message in kafka_consumer:
        kafka_topic = message.topic
        payload = message.value
        
        try:
            mac = get_mac_from_payload(payload)
            if not mac:
                print(f"--> WARNING: Bo qua tin nhan tu topic '{kafka_topic}' vi khong tim thay MAC address.")
                continue

            # Ánh xạ từ Kafka topic sang MQTT topic
            if kafka_topic == 'raw_sensor_data':
                mqtt_topic = f"sensors/raw/{mac}"
            elif kafka_topic == 'ai_predictions':
                mqtt_topic = f"sensors/predictions/{mac}"
            else:
                # Bỏ qua nếu có topic lạ trong Kafka
                continue

            # Chuyển đổi payload thành chuỗi JSON để publish
            mqtt_payload = json.dumps(payload)
            
            # Gửi tin nhắn
            result = mqtt_client.publish(mqtt_topic, mqtt_payload)
            # Đảm bảo tin nhắn đã được gửi đi trước khi xử lý tiếp
            result.wait_for_publish()

            if result.is_published():
                 print(f"Chuyen tiep: Kafka '{kafka_topic}' -> MQTT '{mqtt_topic}'")
            else:
                 print(f"--> ERROR: Gui tin nhan len MQTT topic '{mqtt_topic}' that bai!")

        except Exception as e:
            print(f"--> ERROR: Loi khong xac dinh khi xu ly tin nhan: {e}")

if __name__ == "__main__":
    main()
