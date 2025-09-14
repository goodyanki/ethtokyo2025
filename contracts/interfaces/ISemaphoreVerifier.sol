// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ISemaphoreVerifier
/// @notice 接口：用于验证基于 Semaphore 的成员证明（Groth16）
/// @dev 常见实现来自 semaphore 的 verifier 合约（bn254 配对预编译）
///      这里仅定义接口，具体实现用你生成/引入的 Verifier 合约地址。
interface ISemaphoreVerifier {
    /// @param merkleRoot 群组 Merkle 根（电路公开输入）
    /// @param nullifierHash 防重复标记（电路公开输入）
    /// @param externalNullifier 绑定本次领取上下文（建议= keccak256(escrowId)）
    /// @param signalHash 绑定提现目标（建议= keccak256(abi.encode(escrowId, to))）
    /// @param proof Groth16 证明（8 个 `uint256`）
    /// @dev 若证明无效应 revert
    function verifyProof(
        uint256 merkleRoot,
        uint256 nullifierHash,
        uint256 externalNullifier,
        uint256 signalHash,
        uint256[8] calldata proof
    ) external view;
}
