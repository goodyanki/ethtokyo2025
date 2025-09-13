// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract StealthRegistry {
    event Announce(
        bytes32 Rx,
        bytes32 Ry,
        uint8   viewTag,      // 可留作兼容；若你走 MPC，可填 0
        bytes   memoCipher,
        bytes32 commitment,   // 用于后续 ZK 证明/统计
        bytes16 tag           // 发现用标签（比如 H(shared||salt) 截断 128bit）
    );

    function publish(
        bytes32 Rx,
        bytes32 Ry,
        uint8   viewTag,
        bytes calldata memoCipher,
        bytes32 commitment,
        bytes16 tag
    ) external {
        emit Announce(Rx, Ry, viewTag, memoCipher, commitment, tag);
    }
}
