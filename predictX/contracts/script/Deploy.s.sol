// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/MockUSDC.sol";
import "../src/PDXMarket.sol";
import "../src/PDXOracle.sol";

/// @notice Deploys all PDX contracts to Base Sepolia
contract DeployScript is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        console.log("Deployer:", deployer);
        console.log("Balance:", deployer.balance);

        vm.startBroadcast(deployerKey);

        // 1. Deploy MockUSDC
        MockUSDC usdc = new MockUSDC();
        console.log("MockUSDC:", address(usdc));

        // 2. Deploy PDXMarket (deployer as temp oracle)
        PDXMarket market = new PDXMarket(address(usdc), deployer);
        console.log("PDXMarket:", address(market));

        // 3. Deploy PDXOracle
        PDXOracle oracle = new PDXOracle(address(market));
        console.log("PDXOracle:", address(oracle));

        // 4. Set oracle on market
        market.setOracle(address(oracle));
        console.log("Oracle set on market");

        // 5. Mint test USDC to deployer (100,000 USDC)
        usdc.mint(deployer, 100_000e6);
        console.log("Minted 100,000 USDC to deployer");

        vm.stopBroadcast();

        // Print summary
        console.log("\n=== Deployment Summary ===");
        console.log("MockUSDC:   ", address(usdc));
        console.log("PDXMarket:  ", address(market));
        console.log("PDXOracle:  ", address(oracle));
        console.log("========================\n");
    }
}
