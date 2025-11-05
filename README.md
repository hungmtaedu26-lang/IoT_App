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