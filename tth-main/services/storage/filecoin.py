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

LIGHTHOUSE_UPLOAD_URL = "https://node.lighthouse.storage/api/v0/add"

configure_logging()
logger = logging.getLogger("filecoin_uploader")
settings = get_settings()


def _lighthouse_upload(api_key: str, transcript_file: Path) -> dict:
    headers = {"Authorization": f"Bearer {api_key}"}
    with transcript_file.open("rb") as fp:
        files = {"file": (transcript_file.name, fp, "application/json")}
        response = requests.post(
            LIGHTHOUSE_UPLOAD_URL,
            headers=headers,
            files=files,
            timeout=180,
        )
        response.raise_for_status()
        return response.json()


def _mock_deal(transcript_file: Path) -> tuple[int, str]:
    data = transcript_file.read_bytes()
    deal_id = poseidon_like_hash([int.from_bytes(data[-32:], "big", signed=False)]) % (10 ** 12)
    cid = hex(poseidon_like_hash([int.from_bytes(data[:32], "big", signed=False)]))[2:]
    return deal_id, cid


async def push_to_filecoin(transcript_file: Path) -> bool:
    target_dir = settings.filecoin_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    if settings.lighthouse_api_key:
        loop = asyncio.get_running_loop()
        try:
            response: dict = await loop.run_in_executor(
                None,
                partial(_lighthouse_upload, settings.lighthouse_api_key, transcript_file),
            )
        except RequestException as exc:
            logger.error("Lighthouse upload failed for %s: %s", transcript_file.name, exc)
            return False
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected Lighthouse error for %s", transcript_file.name)
            return False

        data = response.get("data") or {}
        cid = data.get("Hash") or data.get("cid") or data.get("CID")
        if not cid:
            # Fallback: derive deterministic cid-like identifier
            cid = hex(poseidon_like_hash([int.from_bytes(transcript_file.read_bytes()[:32], "big", signed=False)]))[2:]
        deal_entries = response.get("dealStatus") or response.get("dealInfo") or []
        if isinstance(deal_entries, dict):
            deal_entries = [deal_entries]
        deal_id: Optional[str] = None
        for entry in deal_entries:
            deal_id = entry.get("dealId") or entry.get("deal_id") or entry.get("deal")
            if deal_id:
                break
        record = {
            "provider": "lighthouse",
            "cid": cid,
            "transcript": transcript_file.name,
            "deal_id": deal_id,
            "response": response,
        }
        filename = f"lighthouse_{cid}.json"
    else:
        deal_id, cid = _mock_deal(transcript_file)
        record = {
            "provider": "mock",
            "cid": cid,
            "transcript": transcript_file.name,
            "deal_id": deal_id,
            "status": "submitted",
        }
        filename = f"deal_{deal_id}.json"

    output_path = target_dir / filename
    output_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    logger.info(
        "Filed transcript %s to Filecoin via %s (deal_id=%s, cid=%s)",
        transcript_file.name,
        record["provider"],
        record.get("deal_id"),
        record["cid"],
    )
    return True


async def monitor() -> None:
    processed: Set[str] = set()
    settings.transcripts_dir.mkdir(parents=True, exist_ok=True)
    settings.filecoin_dir.mkdir(parents=True, exist_ok=True)

    async for changes in awatch(settings.transcripts_dir):
        for _, path in changes:
            path_obj = Path(path)
            if path_obj.suffix != ".json":
                continue
            if path_obj.name in processed:
                continue
            success = await push_to_filecoin(path_obj)
            if success:
                processed.add(path_obj.name)


def main() -> None:
    asyncio.run(monitor())


if __name__ == "__main__":
    main()


