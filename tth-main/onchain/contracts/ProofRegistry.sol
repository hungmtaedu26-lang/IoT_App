// SPDX-License-Identifier: MIT
pragma solidity ^0.8.18;

contract ProofRegistry {
    event ProofVerified(bytes32 indexed traceId, uint256 amount, uint256 senderAfter, uint256 receiverAfter, string cid);

    mapping(bytes32 => bool) public verified;

    function recordProof(
        bytes32 traceId,
        uint256 amount,
        uint256 senderAfter,
        uint256 receiverAfter,
        string calldata cid
    ) external {
        require(!verified[traceId], "TRACE_ALREADY_RECORDED");
        verified[traceId] = true;
        emit ProofVerified(traceId, amount, senderAfter, receiverAfter, cid);
    }
}
