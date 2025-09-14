// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "openzeppelin-contracts/contracts/utils/cryptography/ECDSA.sol";
import "openzeppelin-contracts/contracts/utils/ReentrancyGuard.sol";
import "openzeppelin-contracts/contracts/access/Ownable.sol";

contract PaymentProxy is ReentrancyGuard, Ownable {
    using ECDSA for bytes32;

    address public mpcSigner;

    // tag -> 在本合约中托管的余额（单位：wei）
    mapping(bytes32 => uint256) public taggedBalances;

    // 防重放：记录 paymentId 是否已花费
    mapping(bytes32 => bool) public spent;

    event PaymentAnnounced(bytes32 indexed tag, bytes R, bytes memoCipher, uint256 amount);
    event PaymentSpent(bytes32 indexed paymentId, address indexed to, uint256 amount);

    constructor(address _mpcSigner) Ownable(msg.sender) {
        mpcSigner = _mpcSigner;
    }

    function setMpcSigner(address _mpcSigner) external onlyOwner {
        mpcSigner = _mpcSigner;
    }

    /// @notice 上链公告并托管 ETH（发送方用自己的测试账户直接打钱进来）
    /// @dev msg.value 就是托管的金额，累加到该 tag 的余额上
    function announcePayment(bytes32 tag, bytes calldata R, bytes calldata memoCipher) external payable {
        // 可以加额外校验，比如 msg.value > 0
        taggedBalances[tag] += msg.value;
        emit PaymentAnnounced(tag, R, memoCipher, msg.value);
    }

    /// @notice 花费（把托管在 tag 下的 ETH 转到 to）
    ///         由 MPC ECDSA 签名授权后才能转出
    function spend(
        bytes32 paymentId,
        address payable to,
        uint256 amount,
        bytes32 tag,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external nonReentrant {
        // 构造与后端一致的 digest（raw digest，无 \x19 前缀）
        bytes32 digest = keccak256(abi.encodePacked(paymentId, to, amount, tag));

        address recovered = ecrecover(digest, v, r, s);
        require(recovered == mpcSigner, "invalid MPC signature");

        require(!spent[paymentId], "already spent");
        require(taggedBalances[tag] >= amount, "insufficient tagged balance");

        // 扣减余额 + 标记已花费
        taggedBalances[tag] -= amount;
        spent[paymentId] = true;

        // 转给收款地址
        (bool ok, ) = to.call{value: amount}("");
        require(ok, "ETH transfer failed");

        emit PaymentSpent(paymentId, to, amount);
    }

    // 可选：紧急取回（演示用；生产要权限控制）
    function emergencyWithdraw(bytes32 tag, address payable to, uint256 amount) external onlyOwner {
        require(taggedBalances[tag] >= amount, "insufficient tagged balance");
        taggedBalances[tag] -= amount;
        (bool ok, ) = to.call{value: amount}("");
        require(ok, "withdraw failed");
    }

    receive() external payable {}
}
