// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./PDXMarket.sol";

/// @title PDXOracle — Demo settlement oracle (owner-settle)
/// @notice For MVP: owner manually calls settle after checking Polymarket result.
///         Production: replace with Chainlink Functions callback.
contract PDXOracle {
    PDXMarket public immutable market;
    address public owner;

    error OnlyOwner();

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    constructor(address market_) {
        market = PDXMarket(market_);
        owner = msg.sender;
    }

    /// @notice Settle a market with the given outcome
    /// @param marketId The market to settle
    /// @param outcome true = YES wins, false = NO wins
    function settleMarket(uint256 marketId, bool outcome) external onlyOwner {
        market.settle(marketId, outcome);
    }
}
