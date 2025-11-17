from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator


class TransferRequest(BaseModel):
    sender_balance: PositiveInt = Field(..., description="Balance of sender before transfer")
    receiver_balance: int = Field(0, description="Balance of receiver before transfer")
    amount: PositiveInt = Field(..., description="Amount to transfer")
    trace_id: Optional[str] = Field(None, description="Correlation id for logging")

    @field_validator("receiver_balance")
    @classmethod
    def validate_receiver(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Receiver balance cannot be negative")
        return value


class TransferProof(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, json_encoders={Path: lambda v: str(v)})

    trace_id: str
    proof_path: Path
    public_path: Path
    witness_path: Path
    created_at: datetime
    commitments: Dict[str, int]
    meta: Dict[str, Any] = Field(default_factory=dict)


class TransferResponse(BaseModel):
    sender_balance: int
    receiver_balance: int
    proof: TransferProof
    fact_time_ms: float
    total_time_ms: float
    meta: Dict[str, Any] = Field(default_factory=dict)


class DeviceBUpdate(BaseModel):
    receiver_balance: int


class DeviceBState(BaseModel):
    receiver_balance: int
    updated_at: datetime
