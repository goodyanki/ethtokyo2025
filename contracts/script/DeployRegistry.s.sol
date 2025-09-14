// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/StealthRegistry.sol";  // 确保导入路径正确

contract DeployRegistry is Script {
    function run() external {
        vm.startBroadcast();
        
        // 修改为正确的合约名称
        StealthRegistryV2 registry = new StealthRegistryV2();
        
        vm.stopBroadcast();
        
        // 打印部署地址
        console2.log("StealthRegistryV2 deployed at:", address(registry));
    }
}