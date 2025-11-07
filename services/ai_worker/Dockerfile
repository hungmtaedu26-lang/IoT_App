# Sử dụng một base image Python gọn nhẹ và ổn định
FROM python:3.9-slim

# Thiết lập thư mục làm việc bên trong container
WORKDIR /app

# Sao chép file requirements.txt vào trước để tận dụng Docker cache
COPY requirements.txt .

# Chạy lệnh pip để cài đặt tất cả các thư viện cần thiết
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ code của service (chủ yếu là main.py) vào thư mục làm việc
COPY . .

# Lệnh mặc định sẽ được thực thi khi container được khởi động
CMD ["python", "main.py"]