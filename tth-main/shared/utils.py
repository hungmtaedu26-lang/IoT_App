from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Iterable


def generate_trace_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def monotonic_ms() -> int:
    return int(time.perf_counter() * 1000)


def random_field_element(bits: int = 251) -> int:
    if bits <= 0:
        raise ValueError("bits must be positive")
    return secrets.randbits(bits)


def poseidon_like_hash(values: Iterable[int]) -> int:
    hasher = hashlib.sha256()
    for value in values:
        hasher.update(int(value).to_bytes(32, byteorder="big", signed=False))
    return int.from_bytes(hasher.digest(), byteorder="big")

