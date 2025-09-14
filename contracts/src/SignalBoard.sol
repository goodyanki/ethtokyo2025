// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice 把 R 的压缩点拆成 (rx, yParity) 广播，顺带放 tag（便于你 scanner 直接筛）
contract SignalBoard {
    /// @dev R 压缩点：prefix(0x02/0x03) + rx(32B)；这里为了省 gas 只存 rx 和 yParity
    event Signal(bytes32 indexed rx, bool yParity, bytes32 indexed tag, bytes memo);

    function post(bytes32 rx, bool yParity, bytes calldata memo, bytes32 tag) external {
        emit Signal(rx, yParity, tag, memo);
    }
}
