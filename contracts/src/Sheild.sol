// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// 动态输入的通用接口（保留给 spend 流程，如后续需要）
interface IVerifier {
    function verifyProof(
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[] calldata publicInputs
    ) external view returns (bool);
}

// income 阈值验证器的固定签名（与 snarkjs 导出的 Groth16Verifier 匹配）
interface IIncomeVerifier {
    function verifyProof(
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[2] calldata publicInputs
    ) external view returns (bool);
}

contract Shield {
    IVerifier public immutable spendVerifier;    // VerifierSpend.sol（可选）
    IIncomeVerifier public immutable incomeVerifier; // VerifierIncome.sol（固定 2 个 public inputs）

    mapping(bytes32 => bool) public nullified;  // 记录已花费 note

    event Spent(bytes32 nullifier, address to);
    event IncomeProofChecked(address who, bool ok);

    constructor(address _spendVerifier, address _incomeVerifier) {
        spendVerifier = IVerifier(_spendVerifier);
        incomeVerifier = IIncomeVerifier(_incomeVerifier);
    }

    // 最小花费：只做“未双花 + 证明通过”，演示用；如需资金托管再扩展 payable/transfer 逻辑。
    function spend(
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[] calldata publicInputs, // 按电路顺序，比如 [root, bucket/amountPublic, ... , nullifierAsUint]
        bytes32 nullifier,
        address to
    ) external {
        require(!nullified[nullifier], "double-spend");
        bool ok = spendVerifier.verifyProof(a,b,c,publicInputs);
        require(ok, "invalid-proof");

        nullified[nullifier] = true;
        emit Spent(nullifier, to);

        // 可选：如果你托管资金，这里执行转账/释放逻辑
        // (bool s,) = to.call{value: amount}("");
        // require(s);
    }

    // 可选：链上验证“收入 >= X”的阈值证明（如果你想链上验；否则在前端/后端本地验即可）
    function verifyIncome(
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[] calldata publicInputs
    ) external returns (bool) {
        require(publicInputs.length == 2, "bad-public-inputs-len");
        uint256[2] memory pub;
        pub[0] = publicInputs[0];
        pub[1] = publicInputs[1];

        bool ok = incomeVerifier.verifyProof(a, b, c, pub);
        emit IncomeProofChecked(msg.sender, ok);
        return ok;
    }
}
