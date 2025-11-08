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
