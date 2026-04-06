// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @title MockUSDC — Testnet USDC with public minting
/// @notice Anyone can mint tokens for testing purposes
contract MockUSDC is ERC20 {
    constructor() ERC20("USD Coin", "USDC") {}

    /// @notice USDC uses 6 decimals
    function decimals() public pure override returns (uint8) {
        return 6;
    }

    /// @notice Anyone can mint test tokens
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
