import json
import os
import time
import pickle
from datetime import datetime
from pathlib import Path
from collections import deque

import numpy as np
import tensorflow as tf
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

# --- CẤU HÌNH ---
def parse_csv(value: str):
    return [item.strip() for item in value.split(',') if item.strip()]


KAFKA_BROKERS = parse_csv(os.getenv('KAFKA_BROKERS', 'kafka:29092,localhost:9092'))
CONSUMER_TOPIC = 'raw_sensor_data'
PRODUCER_TOPIC = 'ai_predictions'
# Đường dẫn tới các file artifact (ưu tiên giá trị env, sau đó /models, cuối cùng là ../models)
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
MODEL_CANDIDATES = [
    os.getenv('MODEL_ARTIFACT_PATH'),
    '/models/heart_anomaly_model.pkl',
    str(PROJECT_ROOT / 'models' / 'heart_anomaly_model.pkl'),
]
SCALER_CANDIDATES = [
    os.getenv('SCALER_PATH'),
    '/models/scaler.pkl',
    str(PROJECT_ROOT / 'models' / 'scaler.pkl'),
]

# Các biến này sẽ được tự động điền khi tải model
WINDOW_SIZE = None
NUM_FEATURES = None
SENSOR_COLS_ORDER = None # Lưu lại đúng thứ tự các cột

# Ánh xạ tên cột trong artifact sang payload thực tế từ thiết bị
SENSOR_KEY_ALIAS = {
    'accel_x': 'ax_g',
    'temperature': 'temp',
    'pulse_rate': 'bpm',
    'spo2': 'spo2',
}

# Bộ đệm dữ liệu cho mỗi thiết bị
data_buffers = {}


def resolve_first_existing(candidates):
    for path_str in candidates:
        if not path_str:
            continue
        path = Path(path_str)
        if path.exists():
            return path
    return Path(candidates[-1])

def load_dependencies():
    """
    Tải model từ artifact .pkl (chứa config + weights) và scaler.
    Đồng thời cập nhật các biến cấu hình toàn cục.
    """
    global WINDOW_SIZE, NUM_FEATURES, SENSOR_COLS_ORDER

    model_path = resolve_first_existing(MODEL_CANDIDATES)
    scaler_path = resolve_first_existing(SCALER_CANDIDATES)
    
    while True:
        try:
            # Tải artifact chính chứa model
            with open(model_path, 'rb') as f:
                artifact = pickle.load(f)

            # Dựng lại model từ cấu trúc JSON
            model = tf.keras.models.model_from_json(artifact['model_config'])
            # Nạp các trọng số đã được huấn luyện vào model
            model.set_weights(artifact['weights'])
            
            # Tải scaler
            with open(scaler_path, 'rb') as f:
                scaler = pickle.load(f)
                
            # Cập nhật các biến toàn cục từ metadata trong artifact
            WINDOW_SIZE = artifact['window_size']
            SENSOR_COLS_ORDER = artifact['sensor_cols']
            NUM_FEATURES = len(SENSOR_COLS_ORDER)

            print("Da tai model, scaler và metadata thanh cong.")
            print(f" -> Window Size: {WINDOW_SIZE}")
            print(f" -> Thu tu Features: {SENSOR_COLS_ORDER}")
            return model, scaler

        except Exception as e:
            print(f"LOI: Khong the tai model hoac scaler (dang tim o {model_path}, {scaler_path}), thu lai sau 10 giay... Loi: {e}")
            time.sleep(10)

def create_kafka_connections():
    """Tạo Kafka consumer và producer với cơ chế retry."""
    while True:
        try:
            consumer = KafkaConsumer(
                CONSUMER_TOPIC,
                bootstrap_servers=KAFKA_BROKERS,
                auto_offset_reset='earliest',
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                group_id='ai-worker-group'
            )
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            print(f"Da ket noi toi Kafka thanh cong! (brokers={KAFKA_BROKERS})")
            return consumer, producer
        except Exception as e:
            print(f"Khong the ket noi toi Kafka ({KAFKA_BROKERS}), thu lai sau 5 giay... Loi: {e}")
            time.sleep(5)

def main():
    print("--- Khoi dong AI Worker ---")
    
    model, scaler = load_dependencies()
    consumer, producer = create_kafka_connections()

    print("Dang cho du lieu tho de phan tich...")
    while True:
        try:
            message_batches = consumer.poll(timeout_ms=1000, max_records=50)
            if not message_batches:
                continue

            for _, messages in message_batches.items():
                for message in messages:
                    data = message.value
                    mac = data.get('mac')

                    if not mac:
                        continue

                    if mac not in data_buffers:
                        data_buffers[mac] = deque(maxlen=WINDOW_SIZE)

                    features = []
                    for col in SENSOR_COLS_ORDER:
                        payload_key = SENSOR_KEY_ALIAS.get(col, col)
                        features.append(data.get(payload_key, 0))
                    data_buffers[mac].append(features)

                    if len(data_buffers[mac]) < WINDOW_SIZE:
                        continue

                    print(f"Bo dem cho MAC {mac} da du ({len(data_buffers[mac])} diem). Tien hanh du doan.")

                    try:
                        sequence = np.array(list(data_buffers[mac]))
                        scaled_sequence = scaler.transform(sequence)
                        input_data = scaled_sequence.reshape(1, WINDOW_SIZE, NUM_FEATURES)

                        probability = model.predict(input_data, verbose=0)[0][0]
                        prediction = 1 if probability >= 0.5 else 0

                        print(f"    -> Xac suat: {probability:.4f} => Du doan: {prediction}")

                        result_payload = {
                            'original_data': data,
                            'prediction': prediction,
                            'probability': float(probability),
                            'analyzed_at': datetime.utcnow().isoformat() + "Z"
                        }
                        producer.send(PRODUCER_TOPIC, result_payload)
                        producer.flush()

                    except Exception as e:
                        print(f"    -> ERROR: Loi khi phan tich du lieu cho MAC {mac}: {e}")

        except (KafkaError, ValueError) as e:
            print(f"--> WARNING: Mat ket noi Kafka ({e}). Dang khoi tao lai consumer/producer...")
            try:
                consumer.close()
            except Exception:
                pass
            try:
                producer.flush()
                producer.close()
            except Exception:
                pass
            time.sleep(5)
            consumer, producer = create_kafka_connections()

if __name__ == "__main__":
    main()
