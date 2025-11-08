import os
import time
from datetime import datetime
from typing import List, Optional

import mysql.connector
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from mysql.connector import Error
from pydantic import BaseModel, Field

# --- CẤU HÌNH ---
# Đọc thông tin kết nối từ biến môi trường của Docker Compose
MYSQL_HOST = os.getenv("MYSQL_HOST", "mariadb")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "iot_data")
MYSQL_USER = os.getenv("MYSQL_USER", "myuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "mypassword")

app = FastAPI(
    title="IoT Real-time Dashboard API",
    description="API cung cấp dữ liệu cảm biến lịch sử từ hệ thống.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    """Tạo kết nối tới CSDL MariaDB, có cơ chế retry."""
    conn = None
    while conn is None:
        try:
            conn = mysql.connector.connect(
                host=MYSQL_HOST,
                database=MYSQL_DATABASE,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD
            )
            return conn
        except Error as e:
            print(f"Loi ket noi CSDL: {e}. Thu lai sau 5 giay...")
            time.sleep(5)

# --- ĐỊNH NGHĨA CÁC MÔ HÌNH DỮ LIỆU (PYDANTIC MODELS) ---
# Giúp FastAPI tự động xác thực và tạo tài liệu cho dữ liệu trả về
class SensorReading(BaseModel):
    id: int
    mac_address: str
    ax_g: Optional[float] = None
    temp: Optional[float] = None
    bpm: Optional[int] = None
    spo2: Optional[int] = None
    validBPM: Optional[bool] = None
    validSPO2: Optional[bool] = None
    finger_detected: Optional[bool] = None
    rssi: Optional[int] = None
    received_at: datetime

    class Config:
        orm_mode = True # Cho phép Pydantic đọc dữ liệu từ các đối tượng ORM/DB

# --- ĐỊNH NGHĨA CÁC ENDPOINT API ---

@app.get("/", summary="Kiểm tra trạng thái của API")
def read_root():
    """Endpoint cơ bản để kiểm tra xem API có đang hoạt động không."""
    return {"status": "ok", "message": "Welcome to the IoT Sensor API!"}


@app.get(
    "/readings/{mac_address}",
    response_model=List[SensorReading],
    summary="Lấy dữ liệu lịch sử của một thiết bị cụ thể"
)
def get_readings_by_mac(
    mac_address: str, 
    limit: int = Query(100, gt=0, le=1000, description="Số lượng bản ghi tối đa muốn lấy."),
    offset: int = Query(0, ge=0, description="Vị trí bắt đầu lấy dữ liệu (để phân trang).")
):
    """
    Truy vấn và trả về một danh sách các bản ghi dữ liệu cảm biến
    từ một địa chỉ MAC cụ thể, được sắp xếp theo thời gian mới nhất trước.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Dich vu CSDL khong kha dung.")
    
    try:
        cursor = conn.cursor(dictionary=True) # dictionary=True để trả về kết quả dạng dict
        query = """
            SELECT * FROM sensor_readings 
            WHERE mac_address = %s 
            ORDER BY received_at DESC 
            LIMIT %s OFFSET %s
        """
        cursor.execute(query, (mac_address, limit, offset))
        results = cursor.fetchall()
        
        if not results:
            # Trả về mã 404 Not Found nếu không có dữ liệu cho MAC address này
            raise HTTPException(status_code=404, detail=f"Khong tim thay du lieu cho MAC: {mac_address}")
            
        return results
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Loi truy van CSDL: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.get("/devices", response_model=List[str], summary="Lấy danh sách các thiết bị đã gửi dữ liệu")
def get_distinct_devices():
    """Trả về một danh sách duy nhất các địa chỉ MAC đã từng gửi dữ liệu lên hệ thống."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Dich vu CSDL khong kha dung.")
    
    try:
        cursor = conn.cursor()
        query = "SELECT DISTINCT mac_address FROM sensor_readings"
        cursor.execute(query)
        # Kết quả trả về là một list các tuple, ví dụ: [('mac1',), ('mac2',)],
        # nên chúng ta cần trích xuất phần tử đầu tiên của mỗi tuple.
        results = [item[0] for item in cursor.fetchall()]
        return results
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Loi truy van CSDL: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
