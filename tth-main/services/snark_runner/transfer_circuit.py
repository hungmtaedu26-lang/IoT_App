from __future__ import annotations

import logging
from typing import Dict, Tuple

from pysnark.runtime import Var, vc_p
from pysnark.runtime import local_witness as witness
from shared.utils import poseidon_like_hash

logger = logging.getLogger(__name__)

def transfer_circuit(
    sender_before: int,
    receiver_before: int,
    sender_after: int,
    receiver_after: int,
    amount: int,
    nonces: Dict[str, int],
) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int]]:
    """
    Circuit for validating a confidential transfer:
    1. Verify sender has sufficient balance
    2. Verify balances are updated correctly
    3. Generate commitments for before/after states
    """
    # Convert inputs to Var
    s_before = Var(sender_before)
    r_before = Var(receiver_before)
    s_after = Var(sender_after)
    r_after = Var(receiver_after)
    amt = Var(amount)

    # Assert sender has sufficient balance
    vc_p(s_before - amt >= 0, msg="Insufficient sender balance")
    
    # Assert balances update correctly
    vc_p(s_before - amt == s_after, msg="Invalid sender balance update")
    vc_p(r_before + amt == r_after, msg="Invalid receiver balance update")
    
    # Assert non-negativity
    vc_p(s_after >= 0, msg="Negative sender balance after transfer")
    vc_p(r_after >= 0, msg="Negative receiver balance after transfer")

    # Create commitments using Poseidon hash
    commitments = {
        "sender_commitment_before": poseidon_like_hash([sender_before, nonces["sender_before"]]),
        "receiver_commitment_before": poseidon_like_hash([receiver_before, nonces["receiver_before"]]),
        "sender_commitment_after": poseidon_like_hash([sender_after, nonces["sender_after"]]),
        "receiver_commitment_after": poseidon_like_hash([receiver_after, nonces["receiver_after"]]),
    }

    # Public outputs
    public = {
        "amount": amount,
        "sender_after": sender_after,
        "receiver_after": receiver_after,
    }

    # Private witness
    private = {
        "sender_before": sender_before,
        "receiver_before": receiver_before,
        "nonces": nonces,
    }

    return public, private, commitments