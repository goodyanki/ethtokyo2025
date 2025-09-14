// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import {PaymentProxy} from "../src/PaymentProxy.sol";

/// Deploys PaymentProxy and prints the address + signer
/// Env:
///   - MPC_SIGNER (address): optional, defaults to Anvil[0]
contract DeployPaymentProxy is Script {
    function run() external {
        address defaultSigner = address(0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266); // anvil[0]
        address signer;
        // Try to read env; if not set, fallback to default
        try vm.envAddress("MPC_SIGNER") returns (address fromEnv) {
            signer = fromEnv;
        } catch {
            signer = defaultSigner;
        }

        vm.startBroadcast();
        PaymentProxy proxy = new PaymentProxy(signer);
        vm.stopBroadcast();

        console2.log("PaymentProxy:", address(proxy));
        console2.log("mpcSigner:", signer);
    }
}
