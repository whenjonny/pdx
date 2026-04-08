// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./PDXMarket.sol";

/// @title PDXMarketV2 — Evidence Staking Extension
/// @notice Extends PDXMarket with stake-backed evidence submissions.
///         Submitters lock USDC alongside their evidence. After settlement,
///         stakes aligned with the winning outcome receive a pro-rata bonus
///         from the losing pool; losing stakes are forfeited.
contract PDXMarketV2 is PDXMarket {
    using SafeERC20 for IERC20;

    // ─── Constants ───────────────────────────────────────────────

    /// @notice Required USDC stake per evidence submission (5 USDC, 6 decimals)
    uint256 public constant EVIDENCE_STAKE = 5e6;

    // ─── State ───────────────────────────────────────────────────

    /// @notice Direction of the staked evidence (true = YES, false = NO)
    mapping(uint256 => mapping(uint256 => bool)) public evidenceIsYes;

    /// @notice Stake amount deposited per evidence (marketId => evidenceIndex => amount)
    mapping(uint256 => mapping(uint256 => uint256)) public evidenceStake;

    /// @notice Whether the stake for a given evidence has been settled
    mapping(uint256 => mapping(uint256 => bool)) public evidenceStakeSettled;

    /// @notice Total USDC staked on the YES direction for a market
    mapping(uint256 => uint256) public totalStakedYes;

    /// @notice Total USDC staked on the NO direction for a market
    mapping(uint256 => uint256) public totalStakedNo;

    // ─── Events ──────────────────────────────────────────────────

    event EvidenceStaked(
        uint256 indexed marketId,
        address indexed submitter,
        uint256 evidenceIndex,
        bool isYes,
        uint256 amount
    );

    event EvidenceStakeSettled(
        uint256 indexed marketId,
        uint256 evidenceIndex,
        address submitter,
        uint256 payout
    );

    // ─── Errors ──────────────────────────────────────────────────

    error StakeRequired();
    error MarketNotSettled();
    error StakeAlreadySettled();

    // ─── Constructor ─────────────────────────────────────────────

    constructor(address usdc_, address oracle_) PDXMarket(usdc_, oracle_) {}

    // ─── Evidence Staking ────────────────────────────────────────

    /// @notice Submit evidence with a USDC stake backing a directional view
    /// @param marketId The market to submit evidence for
    /// @param ipfsHash IPFS CID of the full evidence report
    /// @param summary Short on-chain summary (< 256 bytes)
    /// @param isYes Direction the submitter believes: true = YES wins, false = NO wins
    function submitEvidenceWithStake(
        uint256 marketId,
        bytes32 ipfsHash,
        string calldata summary,
        bool isYes
    ) external nonReentrant {
        Market storage m = markets[marketId];
        if (m.resolved) revert MarketAlreadyResolved();

        // Transfer stake from submitter
        usdc.safeTransferFrom(msg.sender, address(this), EVIDENCE_STAKE);

        // Replicate parent submitEvidence logic for backward compatibility
        hasEvidence[msg.sender][marketId] = true;

        marketEvidence[marketId].push(Evidence({
            submitter: msg.sender,
            ipfsHash: ipfsHash,
            summary: summary,
            timestamp: block.timestamp
        }));

        uint256 evidenceIndex = marketEvidence[marketId].length - 1;

        emit EvidenceSubmitted(marketId, msg.sender, ipfsHash, summary);

        // Record stake metadata
        evidenceIsYes[marketId][evidenceIndex] = isYes;
        evidenceStake[marketId][evidenceIndex] = EVIDENCE_STAKE;

        if (isYes) {
            totalStakedYes[marketId] += EVIDENCE_STAKE;
        } else {
            totalStakedNo[marketId] += EVIDENCE_STAKE;
        }

        emit EvidenceStaked(marketId, msg.sender, evidenceIndex, isYes, EVIDENCE_STAKE);
    }

    // ─── Stake Settlement ────────────────────────────────────────

    /// @notice Settle all evidence stakes for a resolved market.
    ///         Winners receive their original stake plus a pro-rata share
    ///         of the total losing pool. Losers forfeit their stake.
    /// @param marketId The market to settle stakes for
    function settleEvidenceStakes(uint256 marketId) external {
        Market storage m = markets[marketId];
        if (!m.resolved) revert MarketNotSettled();

        bool winningDirection = m.outcome;
        uint256 winnerPool = winningDirection ? totalStakedYes[marketId] : totalStakedNo[marketId];
        uint256 loserPool = winningDirection ? totalStakedNo[marketId] : totalStakedYes[marketId];

        uint256 evidenceCount = marketEvidence[marketId].length;

        for (uint256 i = 0; i < evidenceCount; i++) {
            // Skip evidence with no stake
            if (evidenceStake[marketId][i] == 0) continue;
            // Skip already-settled stakes
            if (evidenceStakeSettled[marketId][i]) continue;

            evidenceStakeSettled[marketId][i] = true;

            bool stakeIsYes = evidenceIsYes[marketId][i];
            uint256 stakeAmount = evidenceStake[marketId][i];
            address submitter = marketEvidence[marketId][i].submitter;

            if (stakeIsYes == winningDirection) {
                // Winner: refund stake + proportional bonus from losing pool
                uint256 bonus = 0;
                if (winnerPool > 0) {
                    bonus = (loserPool * stakeAmount) / winnerPool;
                }
                uint256 payout = stakeAmount + bonus;
                usdc.safeTransfer(submitter, payout);

                emit EvidenceStakeSettled(marketId, i, submitter, payout);
            } else {
                // Loser: stake forfeited (already held by contract)
                emit EvidenceStakeSettled(marketId, i, submitter, 0);
            }
        }
    }

    // ─── View Functions ──────────────────────────────────────────

    /// @notice Get stake info for a specific evidence submission
    /// @param marketId The market ID
    /// @param evidenceIndex Index of the evidence in the market's evidence array
    /// @return stake The USDC amount staked (0 if submitted without stake)
    /// @return isYes The directional view of the stake
    /// @return settled Whether this stake has been settled
    function getEvidenceStakeInfo(uint256 marketId, uint256 evidenceIndex)
        external
        view
        returns (uint256 stake, bool isYes, bool settled)
    {
        stake = evidenceStake[marketId][evidenceIndex];
        isYes = evidenceIsYes[marketId][evidenceIndex];
        settled = evidenceStakeSettled[marketId][evidenceIndex];
    }
}
