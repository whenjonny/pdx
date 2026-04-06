---
name: pdx_verify
description: "PDX Falsification Bounty Market - Submit propositions with USDC stakes, earn bounties by falsifying claims on Base L2"
version: 0.1.0
user-invocable: true
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env:
        - PDX_WALLET_KEY
      python_packages:
        - web3>=6.0.0
        - requests>=2.31.0
---

# PDX Falsification Bounty Market

A structured Popperian falsification engine with on-chain bounties. Submit propositions by staking USDC, earn bounties by providing high-quality counter-evidence.

## How It Works

1. **Proposers** stake USDC to create falsifiable claims
2. **Falsifiers** search for counter-evidence and submit reports
3. **Reviewers** rate evidence quality
4. **Smart contracts** on Base L2 handle bounty distribution automatically

## Commands

### /pdx-submit <proposition> --stake <amount>

Submit a new proposition to the PDX market with a USDC stake.

1. Parse the proposition for falsifiability (must be specific, verifiable, time-bound)
2. If not falsifiable, suggest improvements
3. Compute content hash (keccak256)
4. Call `scripts/chain.py` to create on-chain proposition
5. Confirm transaction and display proposition ID

**Minimum stake:** 1 USDC | **Maximum stake:** 100,000 USDC

### /pdx-hunt

Browse open propositions available for falsification, sorted by bounty size.

1. Call `scripts/chain.py` to fetch open propositions from Base L2
2. Display sorted by bounty amount (highest first)
3. Show remaining time, current falsification count, and bounty pool

### /pdx-verify <proposition_id>

Execute structured falsification against a specific proposition.

1. Fetch proposition details from chain
2. Parse proposition into verifiable claims
3. Execute multi-angle search strategy:
   - **Breadth:** English news, Chinese news, academic, social media
   - **Depth:** Domain-specific sources, supply chain, financial filings
   - **Red team:** Adversarial search for blind spots
4. Evaluate evidence (5-dimension scoring)
5. Deduplicate (URL → semantic → argument)
6. Generate falsification report with A/B/C/D/F rating
7. Upload report to IPFS via Pinata
8. Submit evidence hash to Base L2 smart contract
9. If evidence quality >= 60, auto-claim bounty

### /pdx-report <proposition_id>

View the falsification report for a proposition.

### /pdx-balance

Check your current PDX earnings and reputation.

## Evidence Scoring (0-100)

| Dimension | Max | Description |
|-----------|-----|-------------|
| Authenticity | 25 | Source reliability |
| Logic | 25 | Argument coherence |
| Authority | 25 | Domain expertise |
| Independence | 15 | Not derived from other evidence |
| Timeliness | 10 | Recency |

## Rating Scale

| Rating | Meaning |
|--------|---------|
| A | Survived rigorous falsification |
| B | Largely credible |
| C | Mixed evidence |
| D | Significant counter-evidence |
| F | Strongly falsified |

## Economic Model

Stake split: 80% bounty pool, 5% protocol, 10% reviewers, 5% creator return.
Bounty: 1st falsifier 50%, 2nd 25%, 3rd 12.5%.

## Network

- **Chain:** Base L2 (Coinbase)
- **Token:** USDC (6 decimals)
- **Gas:** < $0.01 per transaction
