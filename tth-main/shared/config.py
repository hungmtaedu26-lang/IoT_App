from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Centralised runtime configuration for all services."""

    base_dir: Path = Path(__file__).resolve().parents[1]
    data_dir: Path = base_dir / "data"
    proofs_dir: Path = data_dir / "proofs"
    transcripts_dir: Path = data_dir / "transcripts"
    ipfs_dir: Path = data_dir / "ipfs"
    filecoin_dir: Path = data_dir / "filecoin"

    device_a_host: str = os.getenv("DEVICE_A_HOST", "127.0.0.1")
    device_a_port: int = int(os.getenv("DEVICE_A_PORT", "8001"))

    device_b_host: str = os.getenv("DEVICE_B_HOST", "127.0.0.1")
    device_b_port: int = int(os.getenv("DEVICE_B_PORT", "8002"))

    snark_runner_host: str = os.getenv("SNARK_RUNNER_HOST", "127.0.0.1")
    snark_runner_port: int = int(os.getenv("SNARK_RUNNER_PORT", "8003"))

    smart_contract_host: str = os.getenv("SMART_CONTRACT_HOST", "127.0.0.1")
    smart_contract_port: int = int(os.getenv("SMART_CONTRACT_PORT", "8004"))

    device_b_update_url: str = os.getenv(
        "DEVICE_B_UPDATE_URL",
        f"http://{device_b_host}:{device_b_port}/update_balance"
    )
    device_b_state_url: str = os.getenv(
        "DEVICE_B_STATE_URL",
        f"http://{device_b_host}:{device_b_port}/balance"
    )

    snark_runner_verify_url: str = os.getenv(
        "SNARK_RUNNER_VERIFY_URL",
        f"http://{snark_runner_host}:{snark_runner_port}/prove"
    )

    aes_key_hex: str = os.getenv("AES_KEY", "")

    enable_real_snark: bool = os.getenv("ENABLE_REAL_SNARK", "false").lower() in {"1", "true", "yes"}
    pinata_jwt: str = os.getenv("PINATA_JWT", "")
    lighthouse_api_key: str = os.getenv("LIGHTHOUSE_API_KEY", "")
    eth_rpc_url: str = os.getenv("ETH_RPC_URL", "")
    eth_contract_address: str = os.getenv("ETH_CONTRACT_ADDRESS", "")
    eth_private_key: str = os.getenv("ETH_PRIVATE_KEY", "")
    eth_chain_id: int | None = int(os.getenv("ETH_CHAIN_ID", "")) if os.getenv("ETH_CHAIN_ID") else None
    eth_gas_price_gwei: int | None = int(os.getenv("ETH_GAS_PRICE_GWEI", "")) if os.getenv("ETH_GAS_PRICE_GWEI") else None
    eth_max_priority_fee_gwei: int | None = int(os.getenv("ETH_MAX_PRIORITY_FEE_GWEI", "")) if os.getenv("ETH_MAX_PRIORITY_FEE_GWEI") else None

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.proofs_dir, self.transcripts_dir, self.ipfs_dir, self.filecoin_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
