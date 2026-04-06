// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/MockUSDC.sol";
import "../src/PDXMarket.sol";
import "../src/PDXOracle.sol";
import "../src/OutcomeToken.sol";

contract PDXMarketTest is Test {
    MockUSDC usdc;
    PDXMarket market;
    PDXOracle oracle;

    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address carol = makeAddr("carol");

    uint256 constant INITIAL_LIQUIDITY = 10_000e6; // 10,000 USDC
    uint256 constant DEADLINE = 1_000_000;          // future timestamp

    function setUp() public {
        // Warp to a known time
        vm.warp(1000);

        // Deploy contracts
        usdc = new MockUSDC();
        market = new PDXMarket(address(usdc), address(this)); // this contract is temp oracle
        oracle = new PDXOracle(address(market));
        market.setOracle(address(oracle));

        // Fund users
        usdc.mint(alice, 100_000e6);
        usdc.mint(bob, 100_000e6);
        usdc.mint(carol, 100_000e6);

        // Approve market
        vm.prank(alice);
        usdc.approve(address(market), type(uint256).max);
        vm.prank(bob);
        usdc.approve(address(market), type(uint256).max);
        vm.prank(carol);
        usdc.approve(address(market), type(uint256).max);
    }

    // ─── Helpers ─────────────────────────────────────────────────

    function _createDefaultMarket() internal returns (uint256) {
        vm.prank(alice);
        return market.createMarket("Will BTC > 100K?", bytes32(0), DEADLINE, INITIAL_LIQUIDITY);
    }

    // ─── Market Creation ─────────────────────────────────────────

    function test_createMarket() public {
        uint256 aliceBefore = usdc.balanceOf(alice);
        uint256 marketId = _createDefaultMarket();

        assertEq(marketId, 0);
        assertEq(usdc.balanceOf(alice), aliceBefore - INITIAL_LIQUIDITY);

        // Check market state
        (
            , , uint256 reserveYes, uint256 reserveNo, uint256 k,
            uint256 deadline, uint256 lockTime, , , , , , ,
        ) = market.markets(marketId);

        assertEq(reserveYes, INITIAL_LIQUIDITY / 2);
        assertEq(reserveNo, INITIAL_LIQUIDITY / 2);
        assertEq(k, (INITIAL_LIQUIDITY / 2) * (INITIAL_LIQUIDITY / 2));
        assertEq(deadline, DEADLINE);
        assertEq(lockTime, DEADLINE - 30 minutes);

        // Check token deployment
        (address yesAddr, address noAddr) = market.getMarketTokens(marketId);
        assertTrue(yesAddr != address(0));
        assertTrue(noAddr != address(0));
    }

    function test_createMarket_reverts_deadlineTooSoon() public {
        vm.prank(alice);
        vm.expectRevert(PDXMarket.DeadlineTooSoon.selector);
        market.createMarket("test", bytes32(0), block.timestamp + 10, INITIAL_LIQUIDITY);
    }

    function test_createMarket_reverts_insufficientLiquidity() public {
        vm.prank(alice);
        vm.expectRevert(PDXMarket.InsufficientAmount.selector);
        market.createMarket("test", bytes32(0), DEADLINE, 100); // < 1 USDC
    }

    // ─── Trading ─────────────────────────────────────────────────

    function test_buyYes_basic() public {
        uint256 marketId = _createDefaultMarket();

        uint256 bobBefore = usdc.balanceOf(bob);
        vm.prank(bob);
        market.buyYes(marketId, 1000e6); // buy 1000 USDC worth

        // Bob spent USDC
        assertEq(usdc.balanceOf(bob), bobBefore - 1000e6);

        // Bob received YES tokens
        (address yesAddr, ) = market.getMarketTokens(marketId);
        uint256 yesBalance = OutcomeToken(yesAddr).balanceOf(bob);
        assertGt(yesBalance, 0);
    }

    function test_buyNo_basic() public {
        uint256 marketId = _createDefaultMarket();

        vm.prank(bob);
        market.buyNo(marketId, 1000e6);

        (, address noAddr) = market.getMarketTokens(marketId);
        uint256 noBalance = OutcomeToken(noAddr).balanceOf(bob);
        assertGt(noBalance, 0);
    }

    function test_buy_reverts_zeroAmount() public {
        uint256 marketId = _createDefaultMarket();
        vm.prank(bob);
        vm.expectRevert(PDXMarket.ZeroAmount.selector);
        market.buyYes(marketId, 0);
    }

    function test_price_moves_after_buy() public {
        uint256 marketId = _createDefaultMarket();

        uint256 priceBefore = market.getPriceYes(marketId);
        assertEq(priceBefore, 500_000); // 50%

        // Buy YES → YES price should increase
        vm.prank(bob);
        market.buyYes(marketId, 2000e6);

        uint256 priceAfter = market.getPriceYes(marketId);
        assertGt(priceAfter, priceBefore);
    }

    function test_sell_yes() public {
        uint256 marketId = _createDefaultMarket();

        // Bob buys YES
        vm.prank(bob);
        market.buyYes(marketId, 1000e6);

        (address yesAddr, ) = market.getMarketTokens(marketId);
        uint256 yesBalance = OutcomeToken(yesAddr).balanceOf(bob);

        // Bob sells half
        uint256 bobUsdcBefore = usdc.balanceOf(bob);
        vm.prank(bob);
        market.sell(marketId, true, yesBalance / 2);

        assertGt(usdc.balanceOf(bob), bobUsdcBefore);
        assertEq(OutcomeToken(yesAddr).balanceOf(bob), yesBalance - yesBalance / 2);
    }

    // ─── Fee Tiers ───────────────────────────────────────────────

    function test_fee_without_evidence() public {
        uint256 marketId = _createDefaultMarket();

        // Buy without evidence → 0.3% fee
        uint256 buyAmount = 10_000e6;
        vm.prank(bob);
        market.buyYes(marketId, buyAmount);

        (, , , , , , , , uint256 feesAccrued, , , , , ) = market.markets(marketId);
        uint256 expectedFee = (buyAmount * 30) / 10_000; // 0.3%
        assertEq(feesAccrued, expectedFee);
    }

    function test_fee_with_evidence() public {
        uint256 marketId = _createDefaultMarket();

        // Bob submits evidence first
        vm.prank(bob);
        market.submitEvidence(marketId, bytes32("ipfs_hash"), "BTC momentum strong");

        assertTrue(market.hasEvidence(bob, marketId));

        // Buy with evidence → 0.1% fee
        uint256 buyAmount = 10_000e6;
        vm.prank(bob);
        market.buyYes(marketId, buyAmount);

        (, , , , , , , , uint256 feesAccrued, , , , , ) = market.markets(marketId);
        uint256 expectedFee = (buyAmount * 10) / 10_000; // 0.1%
        assertEq(feesAccrued, expectedFee);
    }

    // ─── Evidence ────────────────────────────────────────────────

    function test_submitEvidence() public {
        uint256 marketId = _createDefaultMarket();

        vm.prank(bob);
        market.submitEvidence(marketId, bytes32("hash1"), "Evidence summary");

        assertEq(market.getEvidenceCount(marketId), 1);

        (address submitter, bytes32 ipfsHash, string memory summary, uint256 ts) =
            market.getEvidence(marketId, 0);
        assertEq(submitter, bob);
        assertEq(ipfsHash, bytes32("hash1"));
        assertEq(summary, "Evidence summary");
        assertEq(ts, block.timestamp);
    }

    // ─── Lockdown ────────────────────────────────────────────────

    function test_buy_reverts_after_lockTime() public {
        uint256 marketId = _createDefaultMarket();

        // Warp past lock time
        vm.warp(DEADLINE - 30 minutes);

        vm.prank(bob);
        vm.expectRevert(PDXMarket.MarketLocked.selector);
        market.buyYes(marketId, 1000e6);
    }

    function test_sell_reverts_after_lockTime() public {
        uint256 marketId = _createDefaultMarket();

        // Bob buys before lockdown
        vm.prank(bob);
        market.buyYes(marketId, 1000e6);

        // Warp past lock time
        vm.warp(DEADLINE - 30 minutes);

        (address yesAddr, ) = market.getMarketTokens(marketId);
        uint256 balance = OutcomeToken(yesAddr).balanceOf(bob);

        vm.prank(bob);
        vm.expectRevert(PDXMarket.MarketLocked.selector);
        market.sell(marketId, true, balance);
    }

    function test_evidence_allowed_during_lockdown() public {
        uint256 marketId = _createDefaultMarket();

        // Warp to lockdown period (between lockTime and deadline)
        vm.warp(DEADLINE - 15 minutes);

        // Evidence submission should still work
        vm.prank(bob);
        market.submitEvidence(marketId, bytes32("late_evidence"), "Late but valid");
        assertEq(market.getEvidenceCount(marketId), 1);
    }

    // ─── Settlement & Redemption ─────────────────────────────────

    function test_settle_reverts_before_deadline() public {
        uint256 marketId = _createDefaultMarket();

        vm.expectRevert(PDXMarket.DeadlineNotReached.selector);
        oracle.settleMarket(marketId, true);
    }

    function test_settle_and_redeem_yes_wins() public {
        uint256 marketId = _createDefaultMarket();

        // Bob buys YES, Carol buys NO
        vm.prank(bob);
        market.buyYes(marketId, 5000e6);
        vm.prank(carol);
        market.buyNo(marketId, 3000e6);

        (address yesAddr, address noAddr) = market.getMarketTokens(marketId);
        uint256 bobYes = OutcomeToken(yesAddr).balanceOf(bob);
        uint256 carolNo = OutcomeToken(noAddr).balanceOf(carol);
        assertGt(bobYes, 0);
        assertGt(carolNo, 0);

        // Warp past deadline and settle
        vm.warp(DEADLINE);
        oracle.settleMarket(marketId, true); // YES wins

        // Bob redeems → gets USDC
        uint256 bobUsdcBefore = usdc.balanceOf(bob);
        vm.prank(bob);
        market.redeem(marketId);
        assertEq(usdc.balanceOf(bob), bobUsdcBefore + bobYes);
        assertEq(OutcomeToken(yesAddr).balanceOf(bob), 0); // tokens burned

        // Carol's NO tokens are worthless
        vm.prank(carol);
        vm.expectRevert(PDXMarket.NothingToRedeem.selector);
        market.redeem(marketId);
    }

    function test_settle_and_redeem_no_wins() public {
        uint256 marketId = _createDefaultMarket();

        vm.prank(bob);
        market.buyYes(marketId, 3000e6);
        vm.prank(carol);
        market.buyNo(marketId, 5000e6);

        (, address noAddr) = market.getMarketTokens(marketId);
        uint256 carolNo = OutcomeToken(noAddr).balanceOf(carol);

        // Settle: NO wins
        vm.warp(DEADLINE);
        oracle.settleMarket(marketId, false);

        // Carol redeems
        uint256 carolBefore = usdc.balanceOf(carol);
        vm.prank(carol);
        market.redeem(marketId);
        assertEq(usdc.balanceOf(carol), carolBefore + carolNo);

        // Bob gets nothing
        vm.prank(bob);
        vm.expectRevert(PDXMarket.NothingToRedeem.selector);
        market.redeem(marketId);
    }

    function test_redeem_reverts_before_settlement() public {
        uint256 marketId = _createDefaultMarket();

        vm.prank(bob);
        market.buyYes(marketId, 1000e6);

        vm.prank(bob);
        vm.expectRevert(PDXMarket.MarketNotResolved.selector);
        market.redeem(marketId);
    }

    function test_settle_reverts_double_settle() public {
        uint256 marketId = _createDefaultMarket();

        vm.warp(DEADLINE);
        oracle.settleMarket(marketId, true);

        vm.expectRevert(PDXMarket.MarketAlreadyResolved.selector);
        oracle.settleMarket(marketId, false);
    }

    // ─── Full Lifecycle ──────────────────────────────────────────

    function test_full_lifecycle() public {
        // 1. Alice creates market
        uint256 marketId = _createDefaultMarket();

        // 2. Bob submits evidence and buys YES (0.1% fee)
        vm.startPrank(bob);
        market.submitEvidence(marketId, bytes32("evidence_bob"), "BTC bullish trend");
        market.buyYes(marketId, 5000e6);
        vm.stopPrank();

        // 3. Carol buys NO without evidence (0.3% fee)
        vm.prank(carol);
        market.buyNo(marketId, 5000e6);

        // 4. Verify prices moved
        uint256 yesPrice = market.getPriceYes(marketId);
        // After equal buys on both sides, price stays ~50% but fees affect slightly
        assertGt(yesPrice, 0);
        assertLt(yesPrice, 1e6);

        // 5. Lockdown — trading stops
        vm.warp(DEADLINE - 30 minutes);
        vm.prank(bob);
        vm.expectRevert(PDXMarket.MarketLocked.selector);
        market.buyYes(marketId, 100e6);

        // 6. Settle — YES wins
        vm.warp(DEADLINE);
        oracle.settleMarket(marketId, true);

        // 7. Bob redeems
        (address yesAddr, ) = market.getMarketTokens(marketId);
        uint256 bobYes = OutcomeToken(yesAddr).balanceOf(bob);
        uint256 bobUsdcBefore = usdc.balanceOf(bob);
        vm.prank(bob);
        market.redeem(marketId);
        assertEq(usdc.balanceOf(bob), bobUsdcBefore + bobYes);

        // 8. Carol gets nothing
        vm.prank(carol);
        vm.expectRevert(PDXMarket.NothingToRedeem.selector);
        market.redeem(marketId);
    }
}
