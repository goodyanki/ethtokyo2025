// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/SignalBoard.sol";
import "../src/StealthRegistry.sol";

contract DeployAndEmit is Script {
    function run() external {
        // 用环境变量里的私钥发真实交易
        uint256 pk = vm.envUint("PK");
        vm.startBroadcast(pk); // ❶ 没有这行就只是模拟

        // 部署两个合约（各会发一笔 tx）
        SignalBoard sb = new SignalBoard();
        StealthRegistryV2 reg = new StealthRegistryV2();

        // 示例数据（把你的 R/ tag 换进去即可）
        bytes32 rx = bytes32(uint256(0x1234));
        bool yParity = true;            // R[0] == 0x03
        bytes memory memo = hex"";
        bytes32 tag = keccak256("demo-tag");

        // 还原 R（33B）并演示 Announce
        bytes memory R = abi.encodePacked(bytes1(0x03), rx); // 0x02/0x03 + rx
        bytes memory memoCipher = hex"";
        bytes32 commitment = bytes32(0);

        // 发事件（各一笔 tx）
        sb.post(rx, yParity, memo, tag);
        reg.publish(R, memoCipher, commitment, tag);

        vm.stopBroadcast();
    }
}
