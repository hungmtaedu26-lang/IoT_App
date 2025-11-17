from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict

from shared.utils import poseidon_like_hash

logger = logging.getLogger("snark_backend")


@dataclass
class ProofArtifacts:
    proof: Dict[str, Any]
    public: Dict[str, Any]
    witness: Dict[str, Any]
    commitments: Dict[str, int]


class BaseSnarkBackend:
    name = "base"

    def prove_transfer(
        self,
        sender_before: int,
        receiver_before: int,
        sender_after: int,
        receiver_after: int,
        amount: int,
        nonces: Dict[str, int],
        trace_id: str,
    ) -> ProofArtifacts:  # pragma: no cover - interface only
        raise NotImplementedError


class MockSnarkBackend(BaseSnarkBackend):
    name = "mock-groth16"

    def prove_transfer(
        self,
        sender_before: int,
        receiver_before: int,
        sender_after: int,
        receiver_after: int,
        amount: int,
        nonces: Dict[str, int],
        trace_id: str,
    ) -> ProofArtifacts:
        logger.debug("[%s] Using mock SNARK backend", trace_id)
        commitments = {
            "sender_commitment_before": poseidon_like_hash([sender_before, nonces["sender_before"]]),
            "receiver_commitment_before": poseidon_like_hash([receiver_before, nonces["receiver_before"]]),
            "sender_commitment_after": poseidon_like_hash([sender_after, nonces["sender_after"]]),
            "receiver_commitment_after": poseidon_like_hash([receiver_after, nonces["receiver_after"]]),
        }

        proof = {
            "type": "mock",
            "backend": self.name,
            "trace_id": trace_id,
            "commitments": commitments,
        }

        public = {
            "amount": amount,
            "sender_after": sender_after,
            "receiver_after": receiver_after,
        }

        witness = {
            "sender_before": sender_before,
            "receiver_before": receiver_before,
            "nonces": nonces,
        }

        return ProofArtifacts(proof=proof, public=public, witness=witness, commitments=commitments)


def resolve_backend(enable_real_snark: bool) -> BaseSnarkBackend:
    if enable_real_snark:
        try:
            from .pysnark_backend import PySnarkBackend  # type: ignore

            backend: BaseSnarkBackend = PySnarkBackend()
            logger.info("Using PySNARK backend for proof generation")
            return backend
        except Exception as exc:  # pragma: no cover - fallback
            logger.warning("Falling back to mock backend: %s", exc)

    logger.info("Using mock SNARK backend (no external prover configured)")
    return MockSnarkBackend()

