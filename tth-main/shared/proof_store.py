from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .config import get_settings
from .models import TransferProof
from .utils import utc_now


def write_proof_artifacts(
    trace_id: str,
    proof_payload: Dict,
    public_signals: Dict,
    witness_payload: Dict,
    commitments: Dict[str, int],
    backend: str,
) -> TransferProof:
    settings = get_settings()

    base_path = settings.proofs_dir / trace_id
    base_path.mkdir(parents=True, exist_ok=True)

    proof_path = base_path / "proof.json"
    public_path = base_path / "public.json"
    witness_path = base_path / "witness.json"

    proof_path.write_text(json.dumps(proof_payload, indent=2), encoding="utf-8")
    public_path.write_text(json.dumps(public_signals, indent=2), encoding="utf-8")
    witness_path.write_text(json.dumps(witness_payload, indent=2), encoding="utf-8")

    return TransferProof(
        trace_id=trace_id,
        proof_path=proof_path,
        public_path=public_path,
        witness_path=witness_path,
        created_at=utc_now(),
        commitments=commitments,
        meta={"proof_system": "groth16", "backend": backend},
    )


__all__ = ["write_proof_artifacts"]
