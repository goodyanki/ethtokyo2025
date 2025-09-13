// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import { Shield } from "../src/Sheild.sol";

/// Deploys Shield with provided verifier addresses.
/// Env vars (optional):
///  - SPEND_VERIFIER=0x...
///  - INCOME_VERIFIER=0x...
contract DeployShield is Script {
    function run() external {
        address spend = vm.envOr("SPEND_VERIFIER", address(0));
        address income = vm.envAddress("INCOME_VERIFIER");

        vm.startBroadcast();
        Shield sh = new Shield(spend, income);
        vm.stopBroadcast();

        console2.log("Shield deployed:", address(sh));
        console2.log("  spendVerifier:", spend);
        console2.log("  incomeVerifier:", income);
    }
}

