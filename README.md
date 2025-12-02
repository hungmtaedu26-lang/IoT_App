1. Chạy các dịch vụ trong Docker
docker-compose up -d --build
2.  Chuẩn bị và Chạy Ingestion Service trên Windows
- Di chuyển vào thư mục của ingestion service: 
cd services\ingestion
- Tạo môi trường ảo Python:
python -m venv venv
- Kích hoạt môi trường ảo:
.\venv\Scripts\activate
- Cài đặt các thư viện cần thiết
pip install -r requirements.txt
- Kết nối cổng gateway và chạy chương trình
python main.py
3. heo dõi và Kiểm tra Toàn bộ Luồng
docker-compose logs -f database_worker storage_worker
4. Kiểm tra Dữ liệu:
MariaDB: Mở DBeaver, kết nối tới MariaDB (trên localhost:3300), làm mới (refresh) và xem dữ liệu trong bảng sensor_readings. Bạn sẽ thấy các dòng mới liên tục được thêm vào.
MinIO: Mở trình duyệt và truy cập http://localhost:9001, đăng nhập và bạn sẽ thấy các file JSON mới được tạo ra trong bucket.

5. Dashboard & WebSocket:
- Khi `docker-compose up` chạy HiveMQ, file `hivemq-config/config.xml` được mount vào container và bật listener WebSocket ở cổng `9002` với đường dẫn `/mqtt`.
- Nếu chạy dashboard trên máy Windows (Live Server), cấu hình mặc định đã trỏ tới `ws://localhost:9002/mqtt`. Nếu đổi cổng/host, mở panel ⚙️ (góc trên bên phải dashboard) rồi cập nhật lại.
- HiveMQ Control Center vẫn truy cập tại http://localhost:8080 để kiểm tra kết nối.

6. Chạy các service Python trực tiếp (ngoài Docker):
- Tất cả các service trong thư mục `services/*` tự động thử kết nối tới cả địa chỉ trong Docker (`kafka:29092`, `mariadb`) và localhost (`localhost:9092`, `localhost:3300`). Vì vậy chỉ cần đảm bảo bạn đã chạy `docker-compose up -d` để hạ tầng (Kafka, MariaDB, HiveMQ) hoạt động trên máy.
- Nếu thay đổi port khác mặc định, hãy đặt biến môi trường trước khi chạy, ví dụ:
  - Windows PowerShell:
    ```
    $env:KAFKA_BROKERS="localhost:9092"
    $env:MYSQL_HOST="localhost"
    $env:MYSQL_PORT="3300"
    $env:MQTT_BROKERS="localhost"
    ```
  - CMD:
    ```
    set KAFKA_BROKERS=localhost:9092
    set MYSQL_HOST=localhost
    set MYSQL_PORT=3300
    set MQTT_BROKERS=localhost
    ```
- AI worker sẽ tự động tìm model/scaler ở hai nơi: `/models/*.pkl` (khi chạy trong container) hoặc `../models/*.pkl` (khi chạy trực tiếp tại repo). Nếu lưu ở vị trí khác, đặt thêm `MODEL_ARTIFACT_PATH` và `SCALER_PATH`.

--------------------------
THIẾT LẬP MÔI TRƯỜNG HUẤN LUYỆN
1. Tạo thư mục mới: Tại thư mục gốc iot_realtime_dashboard/, tạo một thư mục mới tên là ai_model_training. Thư mục này sẽ chứa các script Python dùng để huấn luyện mô hình.
2. Tạo Môi trường ảo (Virtual Environment):

Mở Terminal trong VS Code (Ctrl+Shift+`).

Di chuyển vào thư mục mới: cd ai_model_training

Tạo môi trường ảo: python -m venv venv

Kích hoạt môi trường:

(Windows): .\venv\Scripts\activate
3. Cài đặt Thư viện: Dựa trên các tệp notebook của bạn, bạn sẽ cần các thư viện Python. Tạo tệp ai_model_training/requirements.txt với nội dung sau và chạy pip install -r requirements.txt:

pandas
numpy
scikit-learn
xgboost
lightgbm
catboost
joblib
# Thêm các thư viện khác nếu bạn dùng trong notebook

#########
file test_prediction dùng để test chức năng của mô hình AI dự đoán
CÂu lệnh để test
# random một cửa sổ của D1
python test_prediction.py --participant D1

# dùng đúng 64 dòng bắt đầu từ vị trí 128 của N3
python test_prediction.py -p N3 --start 128

==================================
# Thực hiện kiểm tra việc giải mã file đã được mã hóa bởi quantum key distribution
# Lưu ý: Cần chạy bên trong container hoặc môi trường có cài thư viện
docker exec -it filecoin_uploader python verify_encrypted_file.py <TRACE_ID>

# Ví dụ
docker exec -it filecoin_uploader python verify_encrypted_file.py 90:15:06:D7:36:D4_2025-12-02


===================================
Để giải mã file bạn đã tải về bằng key lấy từ DBeaver, tôi đã tạo một công cụ chuyên dụng cho việc này là manual_decrypt.py.

Cách sử dụng:

Cài đặt thư viện (nếu chưa có): Mở terminal (PowerShell) và chạy:
# pip install cryptography
Chạy công cụ:
# python manual_decrypt.py
# Nhập thông tin theo yêu cầu:
# File path: Đường dẫn đến file bạn đã tải về (ví dụ: C:\Downloads\90_15_06_D7_36_D4_2025-12-02_encrypted.bin).
# enc_key: Copy chuỗi trong cột enc_key từ bảng qkd_keys trên DBeaver và paste vào.
# nonce: Copy chuỗi trong cột nonce từ DBeaver và paste vào.
# Chương trình sẽ giải mã và lưu file kết quả ngay tại thư mục đó (đuôi .decrypted.json).