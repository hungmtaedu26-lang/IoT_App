import json
import time
import pickle
import numpy as np
import tensorflow as tf
from kafka import KafkaConsumer, KafkaProducer
from collections import deque

# --- CẤU HÌNH ---
KAFKA_BROKER = 'kafka:29092'
CONSUMER_TOPIC = 'raw_sensor_data'
PRODUCER_TOPIC = 'ai_predictions'
# Đường dẫn tới các file artifact bên trong container Docker
MODEL_ARTIFACT_PATH = '/models/heart_anomaly_model.pkl'
SCALER_PATH = '/models/scaler.pkl'

# Các biến này sẽ được tự động điền khi tải model
WINDOW_SIZE = None
NUM_FEATURES = None
SENSOR_COLS_ORDER = None # Lưu lại đúng thứ tự các cột

# Bộ đệm dữ liệu cho mỗi thiết bị
data_buffers = {}

def load_dependencies(model_path, scaler_path):
    """
    Tải model từ artifact .pkl (chứa config + weights) và scaler.
    Đồng thời cập nhật các biến cấu hình toàn cục.
    """
    global WINDOW_SIZE, NUM_FEATURES, SENSOR_COLS_ORDER
    
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
            print(f"LOI: Khong the tai model hoac scaler, thu lai sau 10 giay... Loi: {e}")
            time.sleep(10)

def create_kafka_connections():
    """Tạo Kafka consumer và producer với cơ chế retry."""
    while True:
        try:
            consumer = KafkaConsumer(
                CONSUMER_TOPIC,
                bootstrap_servers=KAFKA_BROKER,
                auto_offset_reset='earliest',
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                group_id='ai-worker-group'
            )
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            print("Da ket noi toi Kafka thanh cong!")
            return consumer, producer
        except Exception as e:
            print(f"Khong the ket noi toi Kafka, thu lai sau 5 giay... Loi: {e}")
            time.sleep(5)

def main():
    print("--- Khoi dong AI Worker ---")
    
    model, scaler = load_dependencies(MODEL_ARTIFACT_PATH, SCALER_PATH)
    consumer, producer = create_kafka_connections()

    print("Dang cho du lieu tho de phan tich...")
    for message in consumer:
        data = message.value
        mac = data.get('mac')

        if not mac:
            continue
        
        # 1. Thêm dữ liệu mới vào bộ đệm của thiết bị tương ứng
        if mac not in data_buffers:
            data_buffers[mac] = deque(maxlen=WINDOW_SIZE)
        
        # Trích xuất các feature theo đúng thứ tự mà model đã được huấn luyện
        features = [data.get(col, 0) for col in SENSOR_COLS_ORDER]
        data_buffers[mac].append(features)

        # 2. Chỉ dự đoán khi bộ đệm đã có đủ 64 điểm dữ liệu
        if len(data_buffers[mac]) < WINDOW_SIZE:
            continue

        print(f"Bo dem cho MAC {mac} da du ({len(data_buffers[mac])} diem). Tien hanh du doan.")
        
        try:
            # 3. Chuẩn bị dữ liệu đầu vào cho model
            sequence = np.array(list(data_buffers[mac]))
            scaled_sequence = scaler.transform(sequence)
            input_data = scaled_sequence.reshape(1, WINDOW_SIZE, NUM_FEATURES)

            # 4. Thực hiện dự đoán
            probability = model.predict(input_data, verbose=0)[0][0]
            prediction = 1 if probability >= 0.5 else 0

            print(f"    -> Xac suat: {probability:.4f} => Du doan: {prediction}")

            # 5. Gửi kết quả vào topic dự đoán của Kafka
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

if __name__ == "__main__":
    main()