// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/MockUSDC.sol";
import "../src/PDXMarket.sol";

/// @notice Creates a sample prediction market for demo purposes
contract CreateMarketScript is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");

        address usdcAddr = vm.envAddress("MOCK_USDC");
        address marketAddr = vm.envAddress("PDX_MARKET");

        MockUSDC usdc = MockUSDC(usdcAddr);
        PDXMarket market = PDXMarket(marketAddr);

        vm.startBroadcast(deployerKey);

        // Approve market to spend USDC
        usdc.approve(address(market), type(uint256).max);

        // Create market: "Will BTC exceed $100K by June 2026?"
        // Deadline: 30 days from now
        uint256 deadline = block.timestamp + 30 days;
        uint256 initialLiquidity = 10_000e6; // 10,000 USDC

        uint256 marketId = market.createMarket(
            "Will BTC exceed $100K by June 2026?",
            bytes32(0), // no Polymarket link for demo
            deadline,
            initialLiquidity
        );

        console.log("Market created! ID:", marketId);
        console.log("Deadline:", deadline);
        console.log("Initial liquidity: 10,000 USDC");

        vm.stopBroadcast();
    }
}
