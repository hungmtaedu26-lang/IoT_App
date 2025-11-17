from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from watchfiles import awatch

from shared.config import get_settings
from shared.logging import configure_logging

configure_logging()
logger = logging.getLogger("smart_contract_listener")
settings = get_settings()

try:
    from web3 import Web3
    from web3.exceptions import ContractLogicError  # type: ignore
    try:
        from web3.middleware import geth_poa_middleware  # type: ignore
        construct_poa_middleware = None  # type: ignore
    except ImportError:  # pragma: no cover
        geth_poa_middleware = None  # type: ignore
        try:
            from web3.middleware.proof_of_authority import construct_poa_middleware  # type: ignore
        except ImportError:
            construct_poa_middleware = None  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    Web3 = None  # type: ignore
    ContractLogicError = Exception  # type: ignore
    geth_poa_middleware = None  # type: ignore
    construct_poa_middleware = None  # type: ignore
PROOF_REGISTRY_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "traceId", "type": "bytes32"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "uint256", "name": "senderAfter", "type": "uint256"},
            {"internalType": "uint256", "name": "receiverAfter", "type": "uint256"},
            {"internalType": "string", "name": "cid", "type": "string"},
        ],
        "name": "recordProof",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "bytes32", "name": "traceId", "type": "bytes32"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "senderAfter", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "receiverAfter", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "cid", "type": "string"},
        ],
        "name": "ProofVerified",
        "type": "event",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "name": "verified",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class EthereumNotifier:
    def __init__(self, settings) -> None:
        self._logger = logging.getLogger("smart_contract_listener.ethereum")
        self.settings = settings
        self.enabled = False
        self.web3: Optional[Web3] = None  # type: ignore
        self.contract = None
        self.account = None
        self.chain_id: Optional[int] = None
        self.gas_price_override: Optional[int] = None
        self.priority_fee_override: Optional[int] = None

        if Web3 is None:
            self._logger.info("web3.py not installed; Ethereum integration disabled")
            return

        if not (
            settings.eth_rpc_url
            and settings.eth_contract_address
            and settings.eth_private_key
        ):
            self._logger.info(
                "Ethereum integration disabled (missing ETH_RPC_URL / ETH_CONTRACT_ADDRESS / ETH_PRIVATE_KEY)"
            )
            return

        try:
            self.web3 = Web3(Web3.HTTPProvider(settings.eth_rpc_url, request_kwargs={"timeout": 30}))
            if not self.web3.is_connected():  # pragma: no cover - network path
                self._logger.error("Could not connect to Ethereum RPC at %s", settings.eth_rpc_url)
                return

            if geth_poa_middleware is not None:
                self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

            self.account = self.web3.eth.account.from_key(settings.eth_private_key)
            self.contract = self.web3.eth.contract(
                address=self.web3.to_checksum_address(settings.eth_contract_address),
                abi=PROOF_REGISTRY_ABI,
            )
            self.chain_id = settings.eth_chain_id or self.web3.eth.chain_id
            if settings.eth_gas_price_gwei is not None:
                self.gas_price_override = settings.eth_gas_price_gwei * 10**9
            if settings.eth_max_priority_fee_gwei is not None:
                self.priority_fee_override = settings.eth_max_priority_fee_gwei * 10**9

            self.enabled = True
            self._logger.info(
                "Ethereum integration active for %s (contract=%s, chain_id=%s)",
                self.account.address,
                self.contract.address,
                self.chain_id,
            )
        except Exception as exc:  # pragma: no cover - setup failure
            self._logger.error("Failed to initialise Ethereum notifier: %s", exc, exc_info=True)
            self.enabled = False

    def submit_proof(self, trace_id: str, public: Dict[str, int], proof_dir: Path) -> Optional[Dict[str, object]]:
        if not self.enabled or self.web3 is None or self.contract is None or self.account is None:
            return None

        try:
            amount = int(public.get("amount", 0))
            sender_after = int(public.get("sender_after", 0))
            receiver_after = int(public.get("receiver_after", 0))
            cid = self._lookup_cid(trace_id) or ""
            trace_bytes = self._trace_bytes(trace_id)

            func = self.contract.functions.recordProof(trace_bytes, amount, sender_after, receiver_after, cid)
            tx_params = {
                "from": self.account.address,
                "nonce": self.web3.eth.get_transaction_count(self.account.address, "pending"),
                "chainId": self.chain_id,
            }
            tx_params.update(self._fee_config())

            try:
                gas_estimate = func.estimate_gas({"from": self.account.address})
            except ContractLogicError as exc:  # pragma: no cover - contract revert path
                self._logger.warning("recordProof reverted for %s: %s", trace_id, exc)
                return {"error": str(exc)}

            tx_params["gas"] = min(gas_estimate + 50_000, 1_000_000)
            transaction = func.build_transaction(tx_params)
            signed = self.account.sign_transaction(transaction)
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            block_number = getattr(receipt, "blockNumber", getattr(receipt, "block_number", None))

            result = {
                "tx_hash": self.web3.to_hex(tx_hash),
                "block_number": block_number,
                "contract": self.contract.address,
                "chain_id": self.chain_id,
                "cid": cid or None,
            }
            self._logger.info(
                "Submitted proof %s to contract %s (tx=%s, block=%s)",
                trace_id,
                self.contract.address,
                result["tx_hash"],
                block_number,
            )
            return result
        except Exception as exc:  # pragma: no cover - runtime failure
            self._logger.error("Failed to submit proof %s on-chain: %s", trace_id, exc, exc_info=True)
            return {"error": str(exc)}

    def _lookup_cid(self, trace_id: str) -> Optional[str]:
        ipfs_dir = self.settings.ipfs_dir
        if not ipfs_dir.exists():
            return None
        try:
            for metadata_path in ipfs_dir.glob("*.json"):
                try:
                    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                proof_path = payload.get("proof_path")
                if proof_path and trace_id in proof_path:
                    return payload.get("cid")
        except Exception:
            return None
        return None

    def _fee_config(self) -> Dict[str, int]:
        assert self.web3 is not None
        if self.gas_price_override is not None and self.priority_fee_override is None:
            return {"gasPrice": self.gas_price_override}

        priority = self.priority_fee_override or self.web3.to_wei(2, "gwei")
        try:
            base_fee = self.web3.eth.get_block("pending").get("baseFeePerGas")
        except Exception:
            base_fee = None

        if base_fee is None:
            gas_price = self.gas_price_override or self.web3.eth.gas_price
            return {"gasPrice": gas_price}

        if self.gas_price_override is not None:
            max_fee = max(self.gas_price_override, base_fee + priority)
        else:
            max_fee = base_fee + priority * 2

        if max_fee < priority:
            max_fee = priority

        return {"maxFeePerGas": max_fee, "maxPriorityFeePerGas": priority}

    @staticmethod
    def _trace_bytes(trace_id: str) -> bytes:
        try:
            raw = bytes.fromhex(trace_id)
        except ValueError:
            raw = trace_id.encode("utf-8")
        if len(raw) >= 32:
            return raw[:32]
        return raw.ljust(32, b"\0")


eth_notifier = EthereumNotifier(settings)


def verify_proof_folder(proof_dir: Path) -> bool:
    proof_file = proof_dir / "proof.json"
    public_file = proof_dir / "public.json"
    witness_file = proof_dir / "witness.json"

    if not (proof_file.exists() and public_file.exists()):
        logger.debug("Skipping %s - missing proof/public files", proof_dir)
        return False

    try:
        public = json.loads(public_file.read_text(encoding="utf-8"))
        witness = json.loads(witness_file.read_text(encoding="utf-8"))
        proof = json.loads(proof_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("Malformed JSON in %s: %s", proof_dir, exc)
        return False

    sender_before = witness.get("sender_before")
    receiver_before = witness.get("receiver_before")
    amount = public.get("amount")
    sender_after = public.get("sender_after")
    receiver_after = public.get("receiver_after")

    if None in (sender_before, receiver_before, amount, sender_after, receiver_after):
        logger.error("Missing fields in proof artefacts: %s", proof_dir)
        return False

    if sender_before - amount != sender_after:
        logger.error("Proof invariant failed: sender balances mismatch for %s", proof_dir)
        return False

    if receiver_before + amount != receiver_after:
        logger.error("Proof invariant failed: receiver balances mismatch for %s", proof_dir)
        return False

    transcript = {
        "status": "verified",
        "proof": proof,
        "public": public,
        "witness": {k: v for k, v in witness.items() if k != "nonces"},
    }

    on_chain = eth_notifier.submit_proof(proof_dir.name, public, proof_dir)
    if on_chain:
        transcript["on_chain"] = on_chain

    transcript_path = settings.transcripts_dir / f"{proof_dir.name}.json"
    transcript_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    logger.info("Verified proof %s and stored transcript", proof_dir.name)
    return True


async def monitor_proofs() -> None:
    logger.info("Watching %s for new proofs", settings.proofs_dir)
    settings.proofs_dir.mkdir(parents=True, exist_ok=True)
    processed: set[str] = set()

    async for changes in awatch(settings.proofs_dir):
        for _, path in changes:
            path_obj = Path(path)
            proof_dir = path_obj if path_obj.is_dir() else path_obj.parent
            if proof_dir.name in processed:
                continue
            if verify_proof_folder(proof_dir):
                processed.add(proof_dir.name)
                logger.debug("Proof %s verified", proof_dir)


def main() -> None:
    asyncio.run(monitor_proofs())


if __name__ == "__main__":
    main()












