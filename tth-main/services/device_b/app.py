from __future__ import annotations

import logging
from threading import Lock

from fastapi import FastAPI, HTTPException

from shared.config import get_settings
from shared.logging import configure_logging
from shared.models import DeviceBState, DeviceBUpdate
from shared.utils import utc_now

configure_logging()
logger = logging.getLogger("device_b")
settings = get_settings()
lock = Lock()

INITIAL_BALANCE = 150
_state = DeviceBState(receiver_balance=INITIAL_BALANCE, updated_at=utc_now())

app = FastAPI(title="Device B Receiver", version="1.0.0")


@app.get("/")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/balance", response_model=DeviceBState)
async def get_balance() -> DeviceBState:
    with lock:
        return _state


@app.post("/update_balance", response_model=DeviceBState)
async def update_balance(payload: DeviceBUpdate) -> DeviceBState:
    if payload.receiver_balance < 0:
        raise HTTPException(status_code=400, detail="Receiver balance cannot be negative")

    with lock:
        logger.info("Updating receiver balance from %s to %s", _state.receiver_balance, payload.receiver_balance)
        _state.receiver_balance = payload.receiver_balance
        _state.updated_at = utc_now()
        return _state


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.device_b.app:app",
        host=settings.device_b_host,
        port=settings.device_b_port,
        reload=False,
        factory=False,
    )
