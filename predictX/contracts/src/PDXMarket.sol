// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./OutcomeToken.sol";

/// @title PDXMarket — Evidence-Driven CPMM Prediction Market
/// @notice Core AMM contract for creating markets, trading YES/NO tokens,
///         submitting evidence for fee discounts, and settling against oracle results.
contract PDXMarket is ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ─── Constants ───────────────────────────────────────────────

    uint256 public constant FEE_NORMAL = 30;           // 0.30%
    uint256 public constant FEE_WITH_EVIDENCE = 10;    // 0.10%
    uint256 public constant FEE_DENOMINATOR = 10_000;
    uint256 public constant LOCKDOWN_BUFFER = 30 minutes;
    uint256 public constant MIN_LIQUIDITY = 1e6;       // 1 USDC minimum

    // ─── Structs ─────────────────────────────────────────────────

    struct Market {
        string question;
        bytes32 polymarketConditionId;
        uint256 reserveYes;
        uint256 reserveNo;
        uint256 k;                   // constant product invariant
        uint256 deadline;
        uint256 lockTime;            // = deadline - 30 min
        uint256 totalDeposited;
        uint256 feesAccrued;
        bool resolved;
        bool outcome;                // true = YES wins
        address creator;
        OutcomeToken yesToken;
        OutcomeToken noToken;
        uint256 totalRedeemed;    // tracks cumulative USDC paid out via redeem()
        bool    creatorWithdrawn; // prevents double-withdrawal
    }

    struct Evidence {
        address submitter;
        bytes32 ipfsHash;
        string summary;
        uint256 timestamp;
    }

    // ─── State ───────────────────────────────────────────────────

    IERC20 public immutable usdc;
    address public oracle;
    address public owner;
    uint256 public nextMarketId;

    mapping(uint256 => Market) public markets;
    mapping(uint256 => Evidence[]) public marketEvidence;
    /// @notice Tracks whether a user has submitted evidence for a market (for fee discount)
    mapping(address => mapping(uint256 => bool)) public hasEvidence;

    // ─── Events ──────────────────────────────────────────────────

    event MarketCreated(uint256 indexed marketId, string question, address indexed creator, uint256 deadline);
    event Trade(uint256 indexed marketId, address indexed trader, bool isYes, uint256 usdcIn, uint256 tokensOut, uint256 fee);
    event Sold(uint256 indexed marketId, address indexed trader, bool isYes, uint256 tokensIn, uint256 usdcOut);
    event EvidenceSubmitted(uint256 indexed marketId, address indexed submitter, bytes32 ipfsHash, string summary);
    event MarketSettled(uint256 indexed marketId, bool outcome);
    event Redeemed(uint256 indexed marketId, address indexed user, uint256 amount);
    event CreatorWithdrew(uint256 indexed marketId, address indexed creator, uint256 amount);
    event OracleUpdated(address indexed oldOracle, address indexed newOracle);

    // ─── Errors ──────────────────────────────────────────────────

    error MarketLocked();
    error MarketNotResolved();
    error MarketAlreadyResolved();
    error DeadlineNotReached();
    error DeadlineTooSoon();
    error OnlyOracle();
    error OnlyOwner();
    error InsufficientAmount();
    error InsufficientLiquidity();
    error NothingToRedeem();
    error ZeroAmount();
    error AlreadyClaimed();
    error OnlyCreator();

    // ─── Modifiers ───────────────────────────────────────────────

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    modifier onlyOracle() {
        if (msg.sender != oracle) revert OnlyOracle();
        _;
    }

    modifier tradingOpen(uint256 marketId) {
        Market storage m = markets[marketId];
        if (block.timestamp >= m.lockTime) revert MarketLocked();
        if (m.resolved) revert MarketAlreadyResolved();
        _;
    }

    // ─── Constructor ─────────────────────────────────────────────

    constructor(address usdc_, address oracle_) {
        usdc = IERC20(usdc_);
        oracle = oracle_;
        owner = msg.sender;
    }

    // ─── Admin ───────────────────────────────────────────────────

    function setOracle(address newOracle) external onlyOwner {
        emit OracleUpdated(oracle, newOracle);
        oracle = newOracle;
    }

    // ─── Market Creation ─────────────────────────────────────────

    /// @notice Create a new prediction market
    /// @param question The market question
    /// @param polymarketConditionId Reference to Polymarket condition (for oracle)
    /// @param deadline Unix timestamp when market closes
    /// @param initialLiquidity USDC amount for initial AMM reserves
    function createMarket(
        string calldata question,
        bytes32 polymarketConditionId,
        uint256 deadline,
        uint256 initialLiquidity
    ) external nonReentrant returns (uint256 marketId) {
        if (deadline <= block.timestamp + LOCKDOWN_BUFFER) revert DeadlineTooSoon();
        if (initialLiquidity < MIN_LIQUIDITY) revert InsufficientAmount();

        marketId = nextMarketId++;

        // Transfer USDC from creator
        usdc.safeTransferFrom(msg.sender, address(this), initialLiquidity);

        // Deploy YES and NO tokens
        OutcomeToken yesToken = new OutcomeToken(
            string.concat("PDX YES #", _uint2str(marketId)),
            string.concat("pYES", _uint2str(marketId)),
            address(this)
        );
        OutcomeToken noToken = new OutcomeToken(
            string.concat("PDX NO #", _uint2str(marketId)),
            string.concat("pNO", _uint2str(marketId)),
            address(this)
        );

        // Initialize 50/50 pool
        uint256 half = initialLiquidity / 2;
        yesToken.mint(address(this), half);
        noToken.mint(address(this), half);

        markets[marketId] = Market({
            question: question,
            polymarketConditionId: polymarketConditionId,
            reserveYes: half,
            reserveNo: half,
            k: half * half,
            deadline: deadline,
            lockTime: deadline - LOCKDOWN_BUFFER,
            totalDeposited: initialLiquidity,
            feesAccrued: 0,
            resolved: false,
            outcome: false,
            creator: msg.sender,
            yesToken: yesToken,
            noToken: noToken,
            totalRedeemed: 0,
            creatorWithdrawn: false
        });

        emit MarketCreated(marketId, question, msg.sender, deadline);
    }

    // ─── Trading ─────────────────────────────────────────────────

    /// @notice Buy YES tokens using USDC
    function buyYes(uint256 marketId, uint256 usdcAmount) external nonReentrant tradingOpen(marketId) {
        _buy(marketId, usdcAmount, true);
    }

    /// @notice Buy NO tokens using USDC
    function buyNo(uint256 marketId, uint256 usdcAmount) external nonReentrant tradingOpen(marketId) {
        _buy(marketId, usdcAmount, false);
    }

    function _buy(uint256 marketId, uint256 usdcAmount, bool isYes) internal {
        if (usdcAmount == 0) revert ZeroAmount();
        Market storage m = markets[marketId];

        // Determine fee rate
        uint256 feeRate = hasEvidence[msg.sender][marketId] ? FEE_WITH_EVIDENCE : FEE_NORMAL;
        uint256 fee = (usdcAmount * feeRate) / FEE_DENOMINATOR;
        uint256 netAmount = usdcAmount - fee;

        // Transfer USDC from buyer
        usdc.safeTransferFrom(msg.sender, address(this), usdcAmount);
        m.totalDeposited += netAmount;
        m.feesAccrued += fee;

        // CPMM: calculate tokens out
        uint256 tokensOut;
        if (isYes) {
            // Buying YES: add USDC to NO reserve side (increases NO reserve)
            // new_reserveYes = k / (reserveNo + netAmount)
            // tokensOut = reserveYes - new_reserveYes
            uint256 newReserveYes = m.k / (m.reserveNo + netAmount);
            tokensOut = m.reserveYes - newReserveYes;
            m.reserveYes = newReserveYes;
            m.reserveNo += netAmount;
            m.yesToken.mint(msg.sender, tokensOut);
        } else {
            uint256 newReserveNo = m.k / (m.reserveYes + netAmount);
            tokensOut = m.reserveNo - newReserveNo;
            m.reserveNo = newReserveNo;
            m.reserveYes += netAmount;
            m.noToken.mint(msg.sender, tokensOut);
        }

        emit Trade(marketId, msg.sender, isYes, usdcAmount, tokensOut, fee);
    }

    /// @notice Sell outcome tokens back to the AMM for USDC
    function sell(uint256 marketId, bool isYes, uint256 tokenAmount)
        external
        nonReentrant
        tradingOpen(marketId)
    {
        if (tokenAmount == 0) revert ZeroAmount();
        Market storage m = markets[marketId];

        // CPMM: calculate USDC out
        uint256 usdcOut;
        if (isYes) {
            // Selling YES: add YES tokens to reserveYes, get USDC from reserveNo
            uint256 newReserveNo = m.k / (m.reserveYes + tokenAmount);
            usdcOut = m.reserveNo - newReserveNo;
            m.reserveYes += tokenAmount;
            m.reserveNo = newReserveNo;
            m.yesToken.burn(msg.sender, tokenAmount);
        } else {
            uint256 newReserveYes = m.k / (m.reserveNo + tokenAmount);
            usdcOut = m.reserveYes - newReserveYes;
            m.reserveNo += tokenAmount;
            m.reserveYes = newReserveYes;
            m.noToken.burn(msg.sender, tokenAmount);
        }

        if (usdcOut == 0) revert InsufficientLiquidity();
        m.totalDeposited -= usdcOut;
        usdc.safeTransfer(msg.sender, usdcOut);

        emit Sold(marketId, msg.sender, isYes, tokenAmount, usdcOut);
    }

    // ─── Evidence ────────────────────────────────────────────────

    /// @notice Submit evidence for a market to unlock fee discount
    /// @param marketId The market ID
    /// @param ipfsHash IPFS CID of the full evidence report
    /// @param summary Short on-chain summary (< 256 bytes)
    function submitEvidence(uint256 marketId, bytes32 ipfsHash, string calldata summary) external {
        Market storage m = markets[marketId];
        if (m.resolved) revert MarketAlreadyResolved();

        hasEvidence[msg.sender][marketId] = true;

        marketEvidence[marketId].push(Evidence({
            submitter: msg.sender,
            ipfsHash: ipfsHash,
            summary: summary,
            timestamp: block.timestamp
        }));

        emit EvidenceSubmitted(marketId, msg.sender, ipfsHash, summary);
    }

    // ─── Settlement ──────────────────────────────────────────────

    /// @notice Settle a market (oracle only)
    function settle(uint256 marketId, bool outcome) external onlyOracle {
        Market storage m = markets[marketId];
        if (m.resolved) revert MarketAlreadyResolved();
        if (block.timestamp < m.deadline) revert DeadlineNotReached();

        m.resolved = true;
        m.outcome = outcome;

        emit MarketSettled(marketId, outcome);
    }

    /// @notice Redeem winning tokens for USDC (1:1)
    function redeem(uint256 marketId) external nonReentrant {
        Market storage m = markets[marketId];
        if (!m.resolved) revert MarketNotResolved();

        OutcomeToken winningToken = m.outcome ? m.yesToken : m.noToken;
        uint256 balance = winningToken.balanceOf(msg.sender);
        if (balance == 0) revert NothingToRedeem();

        // Burn winning tokens, transfer USDC 1:1
        m.totalRedeemed += balance;          // track cumulative redeemed
        winningToken.burn(msg.sender, balance);
        usdc.safeTransfer(msg.sender, balance);

        emit Redeemed(marketId, msg.sender, balance);
    }

    // ─── Creator Withdrawal ────────────────────────────────────────

    /// @notice Market creator withdraws all accrued fees + residual liquidity after settlement
    /// @dev Creator (market maker) earns: fees + all loser funds - winner payouts
    ///      Formula: creatorClaim = totalDeposited + feesAccrued - totalRedeemed - userWinPending
    ///      Safety: userWinPending is deducted at call time, so winners can always redeem after.
    function withdrawCreatorFunds(uint256 marketId) external nonReentrant {
        Market storage m = markets[marketId];
        if (msg.sender != m.creator) revert OnlyCreator();
        if (!m.resolved)             revert MarketNotResolved();
        if (m.creatorWithdrawn)      revert AlreadyClaimed();

        m.creatorWithdrawn = true;

        // Determine winning/losing tokens based on settlement outcome
        // m.outcome = true → YES wins; false → NO wins
        OutcomeToken winningToken = m.outcome ? m.yesToken : m.noToken;
        OutcomeToken losingToken  = m.outcome ? m.noToken  : m.yesToken;

        // Calculate creator's claim BEFORE burning (burning changes totalSupply)
        // userWinPending = winning tokens still held by users (not yet redeemed)
        // creatorClaim = all pool USDC - already paid to winners - still owed to winners
        uint256 userWinPending = winningToken.totalSupply() - winningToken.balanceOf(address(this));
        uint256 creatorClaim   = m.totalDeposited + m.feesAccrued
                                 - m.totalRedeemed
                                 - userWinPending;
        m.feesAccrued = 0;

        // Burn contract's winning LP tokens (creator's LP position cleanup)
        uint256 lpWin = winningToken.balanceOf(address(this));
        if (lpWin > 0) winningToken.burn(address(this), lpWin);

        // Burn contract's losing LP tokens (worthless cleanup)
        uint256 lpLose = losingToken.balanceOf(address(this));
        if (lpLose > 0) losingToken.burn(address(this), lpLose);

        if (creatorClaim > 0) usdc.safeTransfer(m.creator, creatorClaim);
        emit CreatorWithdrew(marketId, m.creator, creatorClaim);
    }

    /// @notice Returns estimated claimable amount for the market creator (only meaningful after settlement)
    function getCreatorClaimable(uint256 marketId)
        external view returns (uint256 claimable)
    {
        Market storage m = markets[marketId];
        if (!m.resolved || m.creatorWithdrawn) return 0;
        OutcomeToken winningToken = m.outcome ? m.yesToken : m.noToken;
        uint256 userWinPending = winningToken.totalSupply() - winningToken.balanceOf(address(this));
        uint256 raw = m.totalDeposited + m.feesAccrued - m.totalRedeemed - userWinPending;
        claimable = raw > 0 ? raw : 0;
    }

    // ─── View Functions ──────────────────────────────────────────

    /// @notice Get current YES price (0 to 1e6, representing 0% to 100%)
    function getPriceYes(uint256 marketId) external view returns (uint256) {
        Market storage m = markets[marketId];
        if (m.reserveYes + m.reserveNo == 0) return 5e5; // 50%
        return (m.reserveNo * 1e6) / (m.reserveYes + m.reserveNo);
    }

    /// @notice Get current NO price
    function getPriceNo(uint256 marketId) external view returns (uint256) {
        Market storage m = markets[marketId];
        if (m.reserveYes + m.reserveNo == 0) return 5e5;
        return (m.reserveYes * 1e6) / (m.reserveYes + m.reserveNo);
    }

    /// @notice Get number of evidence submissions for a market
    function getEvidenceCount(uint256 marketId) external view returns (uint256) {
        return marketEvidence[marketId].length;
    }

    /// @notice Get evidence at specific index
    function getEvidence(uint256 marketId, uint256 index)
        external
        view
        returns (address submitter, bytes32 ipfsHash, string memory summary, uint256 timestamp)
    {
        Evidence storage e = marketEvidence[marketId][index];
        return (e.submitter, e.ipfsHash, e.summary, e.timestamp);
    }

    /// @notice Get market token addresses
    function getMarketTokens(uint256 marketId) external view returns (address yesToken, address noToken) {
        Market storage m = markets[marketId];
        return (address(m.yesToken), address(m.noToken));
    }

    // ─── Internal Helpers ────────────────────────────────────────

    function _uint2str(uint256 value) internal pure returns (string memory) {
        if (value == 0) return "0";
        uint256 temp = value;
        uint256 digits;
        while (temp != 0) {
            digits++;
            temp /= 10;
        }
        bytes memory buffer = new bytes(digits);
        while (value != 0) {
            digits -= 1;
            buffer[digits] = bytes1(uint8(48 + uint256(value % 10)));
            value /= 10;
        }
        return string(buffer);
    }
}
