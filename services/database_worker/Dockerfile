# Chọn base image Python
FROM python:3.9-slim

# Đặt thư mục làm việc trong container
WORKDIR /app

# Sao chép file requirements và cài đặt thư viện
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ code của service vào container
COPY . .

# Lệnh sẽ được chạy khi container khởi động
CMD ["python", "main.py"]