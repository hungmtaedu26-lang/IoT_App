import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import mysql.connector
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from mysql.connector import Error
from pydantic import BaseModel, Field, ConfigDict

# --- CẤU HÌNH ---
MYSQL_HOST = os.getenv("MYSQL_HOST", "mariadb")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "iot_data")
MYSQL_USER = os.getenv("MYSQL_USER", "myuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "mypassword")
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
TRANSCRIPTS_DIR = Path(os.getenv("TRANSCRIPTS_DIR", str(DATA_DIR / "transcripts")))
FILECOIN_DIR = Path(os.getenv("FILECOIN_DIR", str(DATA_DIR / "filecoin")))

app = FastAPI(
    title="IoT Real-time Dashboard API",
    description="API cung cấp dữ liệu cảm biến & dự đoán AI cho dashboard.",
    version="1.1.0",
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
                password=MYSQL_PASSWORD,
            )
            return conn
        except Error as e:
            print(f"Loi ket noi CSDL: {e}. Thu lai sau 5 giay...")
            time.sleep(5)


# --- ĐỊNH NGHĨA CÁC MÔ HÌNH DỮ LIỆU ---
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

    model_config = ConfigDict(from_attributes=True)


class AIPrediction(BaseModel):
    id: int
    mac_address: str
    probability: float = Field(..., ge=0.0, le=1.0)
    prediction: int
    bpm: Optional[float] = None
    spo2: Optional[float] = None
    temp: Optional[float] = None
    ax_g: Optional[float] = None
    analyzed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranscriptSummary(BaseModel):
    mac_address: str
    date: date
    trace_id: str
    transcript_path: str
    status: str
    filecoin_cid: Optional[str] = None
    filecoin_deal_id: Optional[str] = None
    filecoin_provider: Optional[str] = None


class TranscriptDetail(BaseModel):
    transcript: Dict[str, Any]
    filecoin: Optional[Dict[str, Any]] = None


# --- ENDPOINTS ---
@app.get("/", summary="Kiểm tra trạng thái của API")
def read_root():
    return {"status": "ok", "message": "Welcome to the IoT Sensor API!"}


@app.get(
    "/readings/{mac_address}",
    response_model=List[SensorReading],
    summary="Lấy dữ liệu lịch sử của một thiết bị cụ thể",
)
def get_readings_by_mac(
    mac_address: str,
    limit: int = Query(100, gt=0, le=1000, description="Số lượng bản ghi tối đa muốn lấy."),
    offset: int = Query(0, ge=0, description="Vị trí bắt đầu lấy dữ liệu (để phân trang)."),
):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Dich vu CSDL khong kha dung.")

    try:
        cursor = conn.cursor(dictionary=True)
        query = (
            """
            SELECT * FROM sensor_readings
            WHERE mac_address = %s
            ORDER BY received_at DESC
            LIMIT %s OFFSET %s
            """
        )
        cursor.execute(query, (mac_address, limit, offset))
        results = cursor.fetchall()
        return results or []
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Loi truy van CSDL: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def _load_json_file(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_transcript_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return TRANSCRIPTS_DIR / path


def _resolve_filecoin_metadata_path(provider: Optional[str], cid: Optional[str], deal_id: Optional[str]) -> Optional[Path]:
    if provider == "lighthouse" and cid:
        return FILECOIN_DIR / f"lighthouse_{cid}.json"
    if provider == "mock" and deal_id:
        return FILECOIN_DIR / f"deal_{deal_id}.json"
    return None


@app.get(
    "/transcripts/{mac_address}",
    response_model=List[TranscriptSummary],
    summary="Danh sách transcript theo thiết bị",
)
def list_transcripts(
    mac_address: str,
    limit: int = Query(100, gt=0, le=365, description="Số ngày tối đa muốn lấy."),
    offset: int = Query(0, ge=0, description="Bỏ qua bao nhiêu ngày đầu tiên."),
):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Dich vu CSDL khong kha dung.")

    try:
        cursor = conn.cursor(dictionary=True)
        query = """
        SELECT mac_address, date, trace_id, transcript_path, status,
               filecoin_cid, filecoin_deal_id, filecoin_provider
        FROM daily_transcripts
        WHERE mac_address = %s
        ORDER BY date DESC
        LIMIT %s OFFSET %s
        """
        cursor.execute(query, (mac_address, limit, offset))
        rows = cursor.fetchall() or []
        return rows
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Loi truy van CSDL: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.get(
    "/transcripts/{mac_address}/{transcript_date}",
    response_model=TranscriptDetail,
    summary="Chi tiết transcript và metadata Filecoin",
)
def get_transcript_detail(mac_address: str, transcript_date: date):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Dich vu CSDL khong kha dung.")

    try:
        cursor = conn.cursor(dictionary=True)
        query = """
        SELECT mac_address, date, trace_id, transcript_path, status,
               filecoin_cid, filecoin_deal_id, filecoin_provider
        FROM daily_transcripts
        WHERE mac_address = %s
          AND date = %s
        LIMIT 1
        """
        cursor.execute(query, (mac_address, transcript_date))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Khong tim thay transcript.")

        transcript_path = _resolve_transcript_path(row["transcript_path"])
        if not transcript_path.exists():
            raise HTTPException(status_code=404, detail="File transcript khong ton tai.")

        transcript_data = _load_json_file(transcript_path)
        metadata_path = _resolve_filecoin_metadata_path(
            row.get("filecoin_provider"),
            row.get("filecoin_cid"),
            row.get("filecoin_deal_id"),
        )
        metadata: Optional[Dict[str, Any]] = None
        if metadata_path and metadata_path.exists():
            metadata = _load_json_file(metadata_path)

        return {"transcript": transcript_data, "filecoin": metadata}
    except HTTPException:
        raise
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Loi truy van CSDL: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.get(
    "/predictions/{mac_address}",
    response_model=List[AIPrediction],
    summary="Lấy lịch sử dự đoán AI của một thiết bị",
)
def get_predictions_by_mac(
    mac_address: str,
    limit: int = Query(100, gt=0, le=1000, description="Số bản ghi dự đoán muốn lấy."),
    offset: int = Query(0, ge=0, description="Vị trí bắt đầu (dùng cho phân trang)."),
):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Dich vu CSDL khong kha dung.")

    try:
        cursor = conn.cursor(dictionary=True)
        query = (
            """
            SELECT * FROM ai_predictions
            WHERE mac_address = %s
            ORDER BY analyzed_at DESC
            LIMIT %s OFFSET %s
            """
        )
        cursor.execute(query, (mac_address, limit, offset))
        results = cursor.fetchall()
        return results or []
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Loi truy van CSDL: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.get("/devices", response_model=List[str], summary="Lấy danh sách các thiết bị đã gửi dữ liệu")
def get_distinct_devices():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Dich vu CSDL khong kha dung.")

    try:
        cursor = conn.cursor()
        query = (
            """
            SELECT mac_address FROM sensor_readings
            UNION
            SELECT mac_address FROM ai_predictions
            """
        )
        cursor.execute(query)
        results = sorted({item[0] for item in cursor.fetchall() if item and item[0]})
        return results
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Loi truy van CSDL: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
