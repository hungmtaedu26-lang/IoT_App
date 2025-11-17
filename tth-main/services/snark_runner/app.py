from __future__ import annotations

import logging
import time
from typing import Any, Dict

import requests
from fastapi import FastAPI, HTTPException

from shared.config import get_settings
from shared.logging import configure_logging
from shared.models import DeviceBUpdate, TransferRequest, TransferResponse
from shared.proof_store import write_proof_artifacts
from shared.utils import generate_trace_id, random_field_element
from services.snark_runner.snark_pipeline import ProofArtifacts, resolve_backend

configure_logging()
logger = logging.getLogger("snark_runner")
settings = get_settings()
backend = resolve_backend(settings.enable_real_snark)

app = FastAPI(title="SNARK Runner", version="1.0.0")


@app.get("/")
async def healthcheck() -> Dict[str, str]:
    return {"status": "ok", "backend": backend.name}


@app.post("/prove", response_model=TransferResponse)
async def prove(payload: TransferRequest) -> TransferResponse:
    if payload.amount > payload.sender_balance:
        raise HTTPException(status_code=400, detail="Sender balance would become negative")

    trace_id = payload.trace_id or generate_trace_id()
    logger.info(
        "[%s] Received transfer prove request: sender=%s receiver=%s amount=%s",
        trace_id,
        payload.sender_balance,
        payload.receiver_balance,
        payload.amount,
    )

    sender_after = payload.sender_balance - payload.amount
    receiver_after = payload.receiver_balance + payload.amount

    nonces = {
        "sender_before": random_field_element(),
        "receiver_before": random_field_element(),
        "sender_after": random_field_element(),
        "receiver_after": random_field_element(),
    }

    start_fact = time.perf_counter()
    try:
        proof_artifacts: ProofArtifacts = backend.prove_transfer(
            sender_before=payload.sender_balance,
            receiver_before=payload.receiver_balance,
            sender_after=sender_after,
            receiver_after=receiver_after,
            amount=payload.amount,
            nonces=nonces,
            trace_id=trace_id,
        )
    except Exception as exc:  # pragma: no cover - backend failure path
        logger.exception("[%s] Proof generation failed", trace_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    fact_time_ms = (time.perf_counter() - start_fact) * 1000
    proof = write_proof_artifacts(
        trace_id=trace_id,
        proof_payload=proof_artifacts.proof,
        public_signals=proof_artifacts.public,
        witness_payload=proof_artifacts.witness,
        commitments=proof_artifacts.commitments,
        backend=backend.name,
    )

    notify_status: Dict[str, Any]
    try:
        response = requests.post(
            settings.device_b_update_url,
            json=DeviceBUpdate(receiver_balance=receiver_after).model_dump(),
            timeout=10,
        )
        response.raise_for_status()
        notify_status = response.json()
    except requests.RequestException as exc:  # pragma: no cover - network path
        notify_status = {"error": str(exc)}
        logger.warning("[%s] Could not notify Device B: %s", trace_id, exc)

    total_time_ms = fact_time_ms  # Device A will augment with end-to-end time

    logger.info(
        "[%s] Proof complete. sender_after=%s receiver_after=%s", trace_id, sender_after, receiver_after
    )

    return TransferResponse(
        sender_balance=sender_after,
        receiver_balance=receiver_after,
        proof=proof,
        fact_time_ms=round(fact_time_ms, 2),
        total_time_ms=round(total_time_ms, 2),
        meta={"device_b": notify_status, "backend": backend.name},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.snark_runner.app:app",
        host=settings.snark_runner_host,
        port=settings.snark_runner_port,
        reload=False,
        factory=False,
    )





