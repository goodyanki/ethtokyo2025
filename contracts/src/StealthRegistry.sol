// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract StealthRegistryV2 {
    /// @notice 统一的公告事件（钱包/扫描器只需监听这一类事件）
    /// @param R              33字节压缩一次性公钥 r·G
    /// @param memoCipher     加密的金额/备注（ECIES到 view 公钥）
    /// @param commitment     可选：给 ZK/统计用
    /// @param tag            32字节发现标签 = keccak256( sha256(s_view · R) )
    event Announce(bytes R, bytes memoCipher, bytes32 commitment, bytes32 tag);

    function publish(
        bytes calldata R,
        bytes calldata memoCipher,
        bytes32 commitment,
        bytes32 tag
    ) external {
        emit Announce(R, memoCipher, commitment, tag);
    }
}
