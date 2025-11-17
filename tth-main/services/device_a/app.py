from __future__ import annotations

import logging
import time
from pathlib import Path
from threading import Lock
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from shared.config import get_settings
from shared.logging import configure_logging
from shared.models import TransferRequest, TransferResponse
from shared.utils import generate_trace_id

configure_logging()
logger = logging.getLogger("device_a")
settings = get_settings()
lock = Lock()

INITIAL_SENDER_BALANCE = 100
state = {"sender_balance": INITIAL_SENDER_BALANCE}

static_root = Path(__file__).resolve().parent / "static"
app = FastAPI(title="Device A Sender", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=static_root), name="static")


@app.get("/")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ui", response_class=HTMLResponse)
async def render_ui() -> HTMLResponse:
    html = (static_root / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/state")
async def get_state() -> dict[str, Any]:
    with lock:
        return dict(state)


@app.post("/transfer", response_model=TransferResponse)
async def initiate_transfer(payload: TransferRequest) -> TransferResponse:
    with lock:
        sender_balance = state["sender_balance"]

    if payload.amount > sender_balance:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    trace_id = payload.trace_id or generate_trace_id()
    logger.info(
        "[%s] Initiating transfer: sender_balance=%s receiver_balance=%s amount=%s",
        trace_id,
        sender_balance,
        payload.receiver_balance,
        payload.amount,
    )

    start = time.perf_counter()
    try:
        response = requests.post(
            settings.snark_runner_verify_url,
            json={
                "sender_balance": sender_balance,
                "receiver_balance": payload.receiver_balance,
                "amount": payload.amount,
                "trace_id": trace_id,
            },
            timeout=120,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("[%s] SNARK runner call failed", trace_id)
        raise HTTPException(status_code=502, detail=f"SNARK runner unavailable: {exc}") from exc

    total_ms = (time.perf_counter() - start) * 1000
    result = TransferResponse.model_validate(response.json())

    with lock:
        state["sender_balance"] = result.sender_balance

    logger.info(
        "[%s] Transfer completed. Sender balance now %s", trace_id, state["sender_balance"]
    )
    result.total_time_ms = total_ms
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.device_a.app:app",
        host=settings.device_a_host,
        port=settings.device_a_port,
        reload=False,
        factory=False,
    )
