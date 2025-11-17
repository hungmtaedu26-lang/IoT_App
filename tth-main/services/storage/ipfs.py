from __future__ import annotations

import asyncio
import json
import logging
from functools import partial
from pathlib import Path
from typing import Optional, Set

import requests
from requests import RequestException
from watchfiles import awatch

from shared.config import get_settings
from shared.logging import configure_logging
from shared.utils import poseidon_like_hash

PINATA_PIN_FILE_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"

configure_logging()
logger = logging.getLogger("ipfs_uploader")
settings = get_settings()


def _pinata_upload(jwt: str, proof_file: Path) -> dict:
    with proof_file.open("rb") as fp:
        files = {"file": (proof_file.name, fp, "application/json")}
        headers = {"Authorization": f"Bearer {jwt}"}
        response = requests.post(
            PINATA_PIN_FILE_URL,
            headers=headers,
            files=files,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()


def _mock_cid(proof_file: Path) -> tuple[str, int]:
    data = proof_file.read_bytes()
    cid_int = poseidon_like_hash([int.from_bytes(data[:32], "big", signed=False)])
    cid = hex(cid_int)[2:]
    return cid, len(data)


async def upload_to_ipfs(proof_dir: Path) -> bool:
    proof_file = proof_dir / "proof.json"
    if not proof_file.exists():
        logger.debug("Skipping %s; proof.json missing", proof_dir)
        return False

    target = settings.ipfs_dir
    target.mkdir(parents=True, exist_ok=True)

    if settings.pinata_jwt:
        loop = asyncio.get_running_loop()
        try:
            response: dict = await loop.run_in_executor(
                None,
                partial(_pinata_upload, settings.pinata_jwt, proof_file),
            )
        except RequestException as exc:
            logger.error("Pinata upload failed for %s: %s", proof_dir.name, exc)
            return False
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected error uploading %s to Pinata", proof_dir.name)
            return False

        cid = response.get("IpfsHash") or response.get("cid")
        if not cid:
            logger.error("Pinata response missing CID for %s: %s", proof_dir, response)
            return False
        try:
            size = int(response.get("PinSize", proof_file.stat().st_size))
        except (TypeError, ValueError):
            size = proof_file.stat().st_size

        payload = {
            "provider": "pinata",
            "cid": cid,
            "size": size,
            "proof_path": str(proof_file),
            "pinata_response": response,
        }
    else:
        cid, size = _mock_cid(proof_file)
        payload = {
            "provider": "mock",
            "cid": cid,
            "size": size,
            "proof_path": str(proof_file),
        }

    output_path = target / f"{payload['cid']}.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Stored proof %s with CID %s via %s", proof_dir.name, payload["cid"], payload["provider"])
    return True


async def monitor() -> None:
    processed: Set[str] = set()
    settings.ipfs_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Watching %s for proof uploads", settings.proofs_dir)

    async for changes in awatch(settings.proofs_dir):
        for _, path in changes:
            proof_dir = Path(path)
            if proof_dir.is_file():
                proof_dir = proof_dir.parent
            if proof_dir.name in processed:
                continue
            success = await upload_to_ipfs(proof_dir)
            if success:
                processed.add(proof_dir.name)


def main() -> None:
    asyncio.run(monitor())


if __name__ == "__main__":
    main()
