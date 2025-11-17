from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from shared.config import get_settings
from services.snark_runner.snark_pipeline import BaseSnarkBackend, resolve_backend


@dataclass
class TransferMetric:
    trace_id: str
    amount: int
    sender_before: int
    receiver_before: int
    prover_time_ms: float
    gas_used: int
    gas_price_gwei: int
    gas_fee_eth: float
    backend: str
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    cid: Optional[str] = None
    contract: Optional[str] = None
    proof_to_transcript_ms: Optional[float] = None
    proof_to_ipfs_ms: Optional[float] = None
    proof_to_filecoin_ms: Optional[float] = None


def resolve_gas_price(settings) -> int:
    if settings.eth_gas_price_gwei is not None:
        return int(settings.eth_gas_price_gwei)
    if settings.eth_max_priority_fee_gwei is not None:
        return max(int(settings.eth_max_priority_fee_gwei) * 2, 30)
    return 30


def estimate_gas(backend_name: str, num_public: int, gas_price_gwei: int) -> tuple[int, int, float]:
    backend_lower = backend_name.lower()
    if "groth16" in backend_lower:
        base_gas = 210_000
        per_public = 8_000
    else:
        base_gas = 120_000
        per_public = 5_000
    gas_used = base_gas + per_public * num_public
    gas_fee_eth = gas_used * gas_price_gwei / 1_000_000_000
    return gas_used, gas_price_gwei, gas_fee_eth


def load_transcript_info(transcripts_dir: Path, trace_id: str) -> tuple[Optional[dict], Optional[Path]]:
    transcript_path = transcripts_dir / f"{trace_id}.json"
    if not transcript_path.exists():
        return None, None
    try:
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        return payload, transcript_path
    except json.JSONDecodeError:
        return None, transcript_path


def find_metadata_by_trace(metadata_dir: Path, trace_id: str) -> Optional[Path]:
    if not metadata_dir.exists():
        return None
    for metadata_path in metadata_dir.glob("*.json"):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        proof_path = payload.get("proof_path") or payload.get("transcript")
        if isinstance(proof_path, str) and trace_id in proof_path:
            return metadata_path
        if payload.get("trace_id") == trace_id:
            return metadata_path
    return None


def compute_latency_ms(reference_path: Path, target_path: Optional[Path]) -> Optional[float]:
    if not reference_path.exists() or target_path is None or not target_path.exists():
        return None
    return max((target_path.stat().st_mtime - reference_path.stat().st_mtime) * 1000, 0.0)


def measure_transfer(
    trace_id: str,
    proof_dir: Path,
    witness_path: Path,
    public_path: Path,
    backend: BaseSnarkBackend,
    gas_price_gwei: int,
    transcripts_dir: Path,
    ipfs_dir: Path,
    filecoin_dir: Path,
    warmup_runs: int = 1,
    measured_runs: int = 5,
) -> TransferMetric | None:
    if not (witness_path.exists() and public_path.exists()):
        return None

    witness = json.loads(witness_path.read_text(encoding="utf-8"))
    public = json.loads(public_path.read_text(encoding="utf-8"))

    required_witness_keys = {"sender_before", "receiver_before"}
    if not required_witness_keys.issubset(witness):
        raise ValueError(f"Witness file {witness_path} missing required fields")

    if "nonces" not in witness or not isinstance(witness["nonces"], dict):
        raise ValueError(f"Witness file {witness_path} missing nonces section")

    sender_before = int(witness["sender_before"])
    receiver_before = int(witness["receiver_before"])
    amount = int(public.get("amount", 0))
    sender_after = int(public.get("sender_after", sender_before - amount))
    receiver_after = int(public.get("receiver_after", receiver_before + amount))

    nonces = {k: int(v) for k, v in witness["nonces"].items()}

    for _ in range(max(0, warmup_runs)):
        backend.prove_transfer(
            sender_before=sender_before,
            receiver_before=receiver_before,
            sender_after=sender_after,
            receiver_after=receiver_after,
            amount=amount,
            nonces=nonces,
            trace_id=trace_id,
        )

    runs: List[float] = []
    for _ in range(measured_runs):
        start = time.perf_counter()
        backend.prove_transfer(
            sender_before=sender_before,
            receiver_before=receiver_before,
            sender_after=sender_after,
            receiver_after=receiver_after,
            amount=amount,
            nonces=nonces,
            trace_id=trace_id,
        )
        runs.append((time.perf_counter() - start) * 1000)

    prover_time_ms = float(mean(runs))
    gas_used, _, gas_fee_eth = estimate_gas(backend.name, len(public), gas_price_gwei)

    transcript_payload, transcript_path = load_transcript_info(transcripts_dir, trace_id)
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    cid: Optional[str] = None
    contract: Optional[str] = None
    if transcript_payload:
        on_chain = transcript_payload.get("on_chain")
        if isinstance(on_chain, dict):
            tx_hash = on_chain.get("tx_hash")
            block_number = on_chain.get("block_number")
            cid = on_chain.get("cid")
            contract = on_chain.get("contract")
        if cid is None:
            public_info = transcript_payload.get("public")
            if isinstance(public_info, dict):
                cid = public_info.get("cid")

    ipfs_metadata_path = find_metadata_by_trace(ipfs_dir, trace_id)
    filecoin_metadata_path = find_metadata_by_trace(filecoin_dir, trace_id)

    proof_to_transcript_ms = compute_latency_ms(public_path, transcript_path)
    proof_to_ipfs_ms = compute_latency_ms(public_path, ipfs_metadata_path)
    proof_to_filecoin_ms = compute_latency_ms(public_path, filecoin_metadata_path)

    return TransferMetric(
        trace_id=trace_id,
        amount=amount,
        sender_before=sender_before,
        receiver_before=receiver_before,
        prover_time_ms=prover_time_ms,
        gas_used=gas_used,
        gas_price_gwei=gas_price_gwei,
        gas_fee_eth=gas_fee_eth,
        backend=backend.name,
        tx_hash=tx_hash,
        block_number=block_number if block_number is not None else None,
        cid=cid,
        contract=contract,
        proof_to_transcript_ms=proof_to_transcript_ms,
        proof_to_ipfs_ms=proof_to_ipfs_ms,
        proof_to_filecoin_ms=proof_to_filecoin_ms,
    )


def sorted_proof_dirs(proofs_dir: Path) -> List[Path]:
    entries: List[Tuple[float, Path]] = []
    for subdir in proofs_dir.iterdir():
        if not subdir.is_dir():
            continue
        public_path = subdir / "public.json"
        if public_path.exists():
            mtime = public_path.stat().st_mtime
        else:
            mtime = subdir.stat().st_mtime
        entries.append((mtime, subdir))
    entries.sort()
    return [path for _, path in entries]


def gather_metrics(
    proofs_dir: Path,
    transcripts_dir: Path,
    ipfs_dir: Path,
    filecoin_dir: Path,
    backend: BaseSnarkBackend,
    gas_price_gwei: int,
) -> list[TransferMetric]:
    metrics: list[TransferMetric] = []
    for subdir in sorted_proof_dirs(proofs_dir):
        trace_id = subdir.name
        witness_path = subdir / "witness.json"
        public_path = subdir / "public.json"
        try:
            metric = measure_transfer(
                trace_id,
                subdir,
                witness_path,
                public_path,
                backend,
                gas_price_gwei,
                transcripts_dir,
                ipfs_dir,
                filecoin_dir,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to measure transfer {trace_id}: {exc}") from exc
        if metric is not None:
            metrics.append(metric)
    return metrics


def render_section(title: str, lines: Iterable[str]) -> list[str]:
    header = [title, "=" * len(title)]
    body = list(lines)
    return header + body + [""] if body else []


def write_report(
    metrics: list[TransferMetric],
    output_path: Path,
    backend_name: str,
    gas_price_gwei: int,
) -> None:
    lines: list[str] = [
        f"Backend: {backend_name}",
        f"Gas price used (gwei): {gas_price_gwei}",
        "",
    ]

    prover_lines = [
        f"{m.trace_id}: amount={m.amount} sender_before={m.sender_before} "
        f"receiver_before={m.receiver_before} avg_prover_ms={m.prover_time_ms:.6f}"
        for m in metrics
    ]

    gas_lines = [
        f"{m.trace_id}: gas_used={m.gas_used} gas_price_gwei={m.gas_price_gwei} "
        f"gas_fee_eth={m.gas_fee_eth:.8f}"
        for m in metrics
    ]

    latency_lines = []
    for m in metrics:
        def fmt(value: Optional[float]) -> str:
            return f"{value:.2f}" if value is not None else 'n/a'

        latency_lines.append(
            f"{m.trace_id}: proof->on_chain_ms={fmt(m.proof_to_transcript_ms)} "
            f"proof->ipfs_ms={fmt(m.proof_to_ipfs_ms)} "
            f"proof->filecoin_ms={fmt(m.proof_to_filecoin_ms)}"
        )

    on_chain_lines = [
        f"{m.trace_id}: tx_hash={m.tx_hash or 'n/a'} block={m.block_number or 'n/a'} cid={m.cid or 'n/a'}"
        for m in metrics
        if m.tx_hash or m.cid
    ]

    lines.extend(render_section("Prover Time (ms)", prover_lines))
    lines.extend(render_section("Gas Fee Estimates", gas_lines))
    lines.extend(render_section("End-to-End Latency (ms)", latency_lines))
    if on_chain_lines:
        lines.extend(render_section("On-chain Submissions", on_chain_lines))

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    settings = get_settings()
    backend = resolve_backend(settings.enable_real_snark)
    proofs_dir = settings.proofs_dir
    transcripts_dir = settings.transcripts_dir
    ipfs_dir = settings.ipfs_dir
    filecoin_dir = settings.filecoin_dir
    gas_price_gwei = resolve_gas_price(settings)
    metrics = gather_metrics(proofs_dir, transcripts_dir, ipfs_dir, filecoin_dir, backend, gas_price_gwei)
    output_path = settings.data_dir / "transfer_metrics.txt"
    write_report(metrics, output_path, backend.name, gas_price_gwei)
    print(f"Wrote report for {len(metrics)} transfers to {output_path}")


if __name__ == "__main__":
    main()
