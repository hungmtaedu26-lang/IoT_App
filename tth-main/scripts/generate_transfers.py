from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from services.snark_runner.snark_pipeline import BaseSnarkBackend, ProofArtifacts, resolve_backend
from shared.config import get_settings
from shared.proof_store import write_proof_artifacts
from shared.utils import generate_trace_id, random_field_element
from services.smart_contract.listener import verify_proof_folder


@dataclass
class TransferState:
    sender_balance: int
    receiver_balance: int


DEFAULT_SENDER = 100
DEFAULT_RECEIVER = 150


def latest_state(proofs_dir: Path) -> TransferState:
    entries: List[Tuple[float, Path]] = []
    for subdir in proofs_dir.iterdir():
        if not subdir.is_dir():
            continue
        public_path = subdir / "public.json"
        if public_path.exists():
            entries.append((public_path.stat().st_mtime, subdir))
    if not entries:
        return TransferState(DEFAULT_SENDER, DEFAULT_RECEIVER)

    entries.sort()
    sender = DEFAULT_SENDER
    receiver = DEFAULT_RECEIVER
    for _, subdir in entries:
        public_path = subdir / "public.json"
        try:
            public = json.loads(public_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        sender = int(public.get("sender_after", sender))
        receiver = int(public.get("receiver_after", receiver))
    return TransferState(sender, receiver)


def perform_transfer(
    backend: BaseSnarkBackend,
    state: TransferState,
    amount: int,
) -> Tuple[str, TransferState]:
    if amount <= 0:
        raise ValueError("Transfer amount must be positive")
    if state.sender_balance < amount:
        raise ValueError(
            f"Insufficient sender balance {state.sender_balance} for amount {amount}"
        )

    sender_before = state.sender_balance
    receiver_before = state.receiver_balance
    sender_after = sender_before - amount
    receiver_after = receiver_before + amount

    nonces = {
        "sender_before": random_field_element(),
        "receiver_before": random_field_element(),
        "sender_after": random_field_element(),
        "receiver_after": random_field_element(),
    }
    trace_id = generate_trace_id()
    artifacts: ProofArtifacts = backend.prove_transfer(
        sender_before=sender_before,
        receiver_before=receiver_before,
        sender_after=sender_after,
        receiver_after=receiver_after,
        amount=amount,
        nonces=nonces,
        trace_id=trace_id,
    )

    proof = write_proof_artifacts(
        trace_id=trace_id,
        proof_payload=artifacts.proof,
        public_signals=artifacts.public,
        witness_payload=artifacts.witness,
        commitments=artifacts.commitments,
        backend=backend.name,
    )

    verify_proof_folder(proof.proof_path.parent)

    new_state = TransferState(sender_after, receiver_after)
    return trace_id, new_state


def ensure_transfers(target_total: int, amount: int = 10) -> None:
    settings = get_settings()
    backend = resolve_backend(settings.enable_real_snark)
    proofs_dir = settings.proofs_dir
    existing = [subdir for subdir in proofs_dir.iterdir() if subdir.is_dir()]
    to_create = max(0, target_total - len(existing))
    if to_create == 0:
        print(f"Already have {len(existing)} transfers; nothing to do.")
        return

    state = latest_state(proofs_dir)
    print(f"Starting from sender={state.sender_balance} receiver={state.receiver_balance}")
    for idx in range(1, to_create + 1):
        trace_id, state = perform_transfer(backend, state, amount)
        print(
            f"[{idx}/{to_create}] Created transfer {trace_id} -> sender={state.sender_balance}"
            f" receiver={state.receiver_balance}"
        )


def main() -> None:
    target_total = 10
    ensure_transfers(target_total=target_total)


if __name__ == "__main__":
    main()
