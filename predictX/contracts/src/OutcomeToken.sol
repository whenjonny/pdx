// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @title OutcomeToken — YES or NO token for a prediction market
/// @notice Minting and burning restricted to the market contract
contract OutcomeToken is ERC20 {
    address public immutable market;

    error OnlyMarket();

    modifier onlyMarket() {
        if (msg.sender != market) revert OnlyMarket();
        _;
    }

    constructor(string memory name_, string memory symbol_, address market_) ERC20(name_, symbol_) {
        market = market_;
    }

    /// @notice Uses same decimals as USDC for 1:1 redemption
    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amount) external onlyMarket {
        _mint(to, amount);
    }

    function burn(address from, uint256 amount) external onlyMarket {
        _burn(from, amount);
    }
}
