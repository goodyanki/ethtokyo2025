// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title IGroupRegistry
/// @notice 群组 Merkle 根注册表接口
/// @dev EscrowVault 会通过它获取最新的群组根
interface IGroupRegistry {
    /// @notice 返回指定 groupId 的当前 Merkle 根
    /// @param groupId 群组标识（如 keccak256("suppliers2025")）
    /// @return root 群组 Merkle 根（uint256 形式，BN254 field 元素）
    function getRoot(bytes32 groupId) external view returns (uint256);

    /// @notice 设置新的 Merkle 根（仅管理员可调用）
    /// @param groupId 群组标识
    /// @param root 新的 Merkle 根
    function setRoot(bytes32 groupId, uint256 root) external;
}
