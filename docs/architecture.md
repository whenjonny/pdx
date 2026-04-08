# System Architecture

> An evidence-driven AI prediction market: users participate in CPMM markets through AI agents that submit evidence and contribute compute power. The MiroFish multi-agent engine aggregates evidence to produce probability predictions, with settlements anchored to Polymarket outcomes.

---

## Architecture Overview

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  AI Agent        │     │  Backend (8000)   │     │  Base Sepolia    │
│  (Claude Code)   │     │  FastAPI          │     │  Chain ID 84532  │
│                  │     │                   │     │                  │
│  /pdx-analyze    │────→│  /api/markets     │────→│  PDXMarket       │
│  /pdx-submit     │────→│  /api/evidence/*  │     │  MockUSDC        │
│  /pdx-trade      │     │  /api/predictions │     │  PDXOracle       │
│                  │     │                   │     │                  │
│  embedding +     │     │  MiroFish V2      │     │                  │
│  Monte Carlo     │     │  Aggregator       │     │                  │
│  (local CPU)     │     │  (incremental)    │     │                  │
└────────┬─────────┘     └──────────────────┘     └──────────────────┘
         │
         │ signing URL
         ▼
┌──────────────────┐     ┌──────────────────┐
│  Frontend (5173) │     │  IPFS (Pinata)   │
│  React + Vite    │     │                  │
│                  │     │  V2 Evidence     │
│  /sign page      │     │  - embedding     │
│  MetaMask signer │     │  - monteCarlo    │
│  auto approve    │     │  - sources       │
└──────────────────┘     └──────────────────┘
```

> See also [`ArchitectureDiagram_Simple.svg`](../ArchitectureDiagram_Simple.svg) for a visual diagram.

---

## Market Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. MARKET CREATION                                              │
│   Market Creator → picks a Polymarket topic                     │
│   → deploys AMM contract, deposits USDC as initial liquidity    │
│   → sets deadline (= Polymarket expiry - 30 min)                │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. PARTICIPATION (retail / institutional via AI Agents)          │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Agent A  │  │ Agent B  │  │ Agent C  │  │ Human D  │        │
│  │ LLM+News │  │ Quant    │  │ Academic │  │ Manual   │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       ▼              ▼              ▼              ▼             │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              PDX AMM (Smart Contract)                │       │
│  │  buy/sell YES/NO tokens (CPMM: x * y = k)           │       │
│  │  optional: attach evidence → reduced fees            │       │
│  │  optional: contribute compute → earn Credits         │       │
│  └──────────────────────────────────────────────────────┘       │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. MIROFISH (multi-agent prediction engine)                     │
│                                                                 │
│  ┌─ User-side distributed compute (free, local CPU) ────┐      │
│  │  Embedding gen  |  Monte Carlo  |  Graph algo  |  CV  │      │
│  └────────────────────────┬──────────────────────────────┘      │
│                           ▼                                     │
│  ┌─ Central coordination (minimal LLM, covered by fees) ─┐     │
│  │  Agent simulation (Top-K)  |  ReACT report  |  Calib.  │     │
│  └────────────────────────┬───────────────────────────────┘     │
│                           ▼                                     │
│            ┌───────────────────────────┐                        │
│            │ Aggregated prob: P(YES)=72%│                        │
│            │ Confidence: HIGH           │                        │
│            └───────────────────────────┘                        │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. LOCKDOWN + SETTLEMENT                                        │
│   deadline - 30 min:  freeze trading                            │
│   deadline:           wait for Polymarket result                │
│   Polymarket resolves: Oracle pushes result → settle()          │
│   redeem:             winners claim USDC                        │
└─────────────────────────────────────────────────────────────────┘
```

### Timeline

```
t=0                                    t=deadline-30min    t=deadline
 │                                           │                │
 │  ◄──── Trading Phase ────►                │                │
 │                                           │                │
 ├── createMarket()                          ├── LOCKDOWN     ├── SETTLEMENT
 │   deposit USDC, initialize AMM            │   halt trading  │   Oracle pushes result
 ├── users trade (buy/sell)                  │   freeze pos.   │   settle() → redeem()
 ├── agents submit evidence                  │   final price   │
 ├── agents contribute compute               │   locked in     │
 ├── MiroFish updates probabilities          │                │
 └───────────────────────────────────────────┘                │
```

---

## Smart Contract Design

### PDXMarket.sol — Core AMM + Evidence

**CPMM (Constant Product Market Maker)**
- Binary markets: YES token + NO token
- Price formula: `priceYes = reserveNo / (reserveYes + reserveNo)`
- Invariant: `reserveYes * reserveNo = k`
- Initial liquidity sets 50/50 odds

```solidity
struct Market {
    string question;
    bytes32 polymarketConditionId;
    uint256 reserveYes;
    uint256 reserveNo;
    uint256 k;
    uint256 deadline;
    uint256 lockTime;        // = deadline - 30 minutes
    uint256 totalDeposited;
    bool resolved;
    bool outcome;            // true = YES wins
    address creator;
}

// Trading (before lockdown)
buyYes(marketId, usdcAmount, evidenceHash?)
buyNo(marketId, usdcAmount, evidenceHash?)
sell(marketId, isYes, tokenAmount)

// Evidence
submitEvidence(marketId, ipfsHash, summary)

// Settlement
settle(marketId, outcome)   // require(msg.sender == oracle)
redeem(marketId)            // winning tokens redeemed 1:1 for USDC
```

### Fees and Incentives

| Condition | Fee |
|-----------|-----|
| No evidence submitted | 0.3% |
| Evidence submitted | 0.1% |

Fee distribution: 60% LP holders · 20% Evidence Pool · 10% Compute Pool · 10% Protocol treasury

### PDXOracle.sol — Settlement

- Production: Chainlink Functions automatically fetches Polymarket outcomes
- Demo: contract owner manually calls `settle()`

### Token Design

- YES / NO Tokens (ERC20): one pair per market, minted and burned by PDXMarket
- After settlement: winning tokens = 1 USDC each; losing tokens = 0

---

## MiroFish Integration

MiroFish is a multi-agent AI prediction engine built on the OASIS simulation framework. In PDX it serves as the shared probability prediction service.

```
User AI Agent                      MiroFish
┌─────────────────────┐           ┌──────────────────────────┐
│ · gather evidence    │  evidence │ · aggregate all evidence  │
│ · local compute      │  ──────→ │ · coordinate distributed  │
│   (embedding, MC,    │  compute  │   tasks                   │
│    graph algorithms) │           │ · central LLM reasoning   │
│ · decide trade dir.  │           │   (simulation + reports)  │
│ · execute trades     │  ←────── │ · output market forecasts │
│                      │  predict  │ · publish analysis report │
│ one agent per user   │           │ one instance per market   │
└─────────────────────┘           └──────────────────────────┘
```

### Pipeline Optimization: Distributed + Minimal LLM

```
User-side distributed (local CPU, $0, ~70% of compute):
  Embedding → Monte Carlo → Graph construction → Graph algorithms → Statistical models → Cross-validation

Central coordination (LLM, ~30% of compute, covered by protocol fees):
  Agent persona generation → Key decision simulation → ReACT report → Probability calibration
```

Cost comparison: fully centralized $15–50/market → PDX distributed $1.5–5/market (~90% LLM cost reduction)

---

## Evidence System

### Submission Flow

1. Agent gathers evidence (news articles, data, analysis)
2. Compute embedding locally (sentence-transformers, 384 dimensions)
3. Run Monte Carlo simulation locally (5,000+ iterations)
4. Upload to IPFS via Pinata → receive a CID
5. Call `PDXMarket.submitEvidence(marketId, ipfsHash, summary)`
6. MiroFish listens for on-chain events, fetches evidence, and updates probabilities

### Evidence V2 Format (stored on IPFS)

```json
{
  "version": "1.0",
  "marketId": "0x...",
  "direction": "YES",
  "confidence": 0.75,
  "embedding": [0.12, -0.34, ...],
  "sources": [{ "url": "...", "title": "...", "credibility": 9.5 }],
  "analysis": "Based on recent data...",
  "compute_contributions": {
    "monte_carlo": { "n_sim": 5000, "mean": 0.72, "ci_95": [0.65, 0.79] }
  }
}
```

---

## Distributed Compute

### Six Distributable Tasks

| Task | Method | Credits |
|------|--------|---------|
| Embedding computation | sentence-transformers (local, ~50 ms per item) | 1 per item |
| Monte Carlo simulation | NumPy random sampling ×10K | 1 per 1,000 runs |
| Graph algorithms | PageRank, Louvain (networkx) | 5 per run |
| Statistical models | Bayesian, ARIMA, Prophet | 3 per model |
| Web scraping | requests + BeautifulSoup + spaCy NER | 2 per URL |
| Cross-validation | Fact-triple comparison, value-range checks | 2 per pair |

### Compute Credits Economy

- 10 credits = 1 fee-free trade (up to 100 USDC)
- 50 credits = early access to MiroFish report (1 hour ahead)
- 100 credits = redeem 0.5 USDC

### Anti-Cheat

- Random audit of 5% of submissions, re-computed centrally for comparison
- Embedding verification: check that vectors match the source text
- Monte Carlo validation: check that distributions are statistically reasonable

---

## Security Model

```
What agents CAN do:                What agents CANNOT do:
─────────────────────              ───────────────────────
- Read market data (public)        - Sign transactions
- Search the web for evidence      - Access private keys
- Compute embeddings locally       - Transfer funds
- Run Monte Carlo locally          - Execute on-chain transactions
- Upload evidence to IPFS          - Approve token spending
- Generate signing URLs            - Access the user's wallet
```

All on-chain actions go through the frontend `/sign` page, where users review and confirm each transaction in MetaMask.

---

## Agent SDK

```python
from pdx_sdk import PDXClient

client = PDXClient(
    rpc_url="https://base-sepolia.g.alchemy.com/v2/...",
    private_key="0x...",
    contract_address="0x...",
)

# Read market data
market = client.get_market(market_id)

# Local compute
embedding = client.compute_embedding(evidence_text)
mc = client.run_monte_carlo(market_id, n_sim=5000)

# Submit evidence and trade
client.submit_evidence(market_id, cid, "Key finding: ...")
client.buy_yes(market_id, usdc_amount=100, evidence_hash=cid)

# Redeem after settlement
client.redeem(market_id)
```

| Command | Description |
|---------|-------------|
| `/pdx-markets` | Browse all active markets |
| `/pdx-analyze <id>` | Deep analysis: web search + embedding + Monte Carlo |
| `/pdx-submit <id> --direction YES\|NO` | Submit V2 evidence → generate signing URL |
| `/pdx-trade <id> --amount <usdc>` | Generate a buy signing URL |
| `/pdx-portfolio` | View market overview |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/markets` | List all markets |
| GET | `/api/markets/{id}` | Get market details |
| POST | `/api/markets` | Create a new market |
| POST | `/api/markets/settle` | Settle a market |
| POST | `/api/markets/mint-usdc` | Mint test USDC |
| GET | `/api/evidence/{marketId}` | List evidence for a market |
| POST | `/api/evidence/upload` | Upload evidence to IPFS |
| GET | `/api/predictions/{marketId}` | Get AI prediction |
| GET | `/api/health` | Health check |

Full interactive docs: http://localhost:8000/docs

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Chain | Base L2 (Sepolia testnet) |
| Contracts | Solidity 0.8.x · Foundry · OpenZeppelin |
| Oracle | Chainlink Functions (production) / Owner settle (demo) |
| AI Engine | MiroFish — multi-agent prediction engine |
| Simulation | OASIS (camel-ai/oasis) |
| Agent SDK | Python 3.12 · web3.py · sentence-transformers |
| Storage | IPFS via Pinata · SQLite (local persistence) |
| Backend | Python 3.10+ · FastAPI · web3.py |
| Frontend | React 19 · TypeScript · Vite · wagmi · viem · Tailwind CSS |
| Test Token | MockUSDC (ERC20) |

---

## Why Blockchain?

| Problem | Pain Point with Traditional Approach | How Blockchain Solves It |
|---------|--------------------------------------|--------------------------|
| Fund custody | Centralized operator must be trusted; risk of exit scam | AMM contract holds funds autonomously |
| Price manipulation | Market makers can operate opaquely | CPMM formula is transparent and on-chain |
| Settlement trust | Outcomes can be tampered with | Oracle results are immutable once committed |
| Evidence auditing | Evidence can be deleted or forged | IPFS hashes stored on-chain; tamper-proof |
| AI transparency | Predictions can be retroactively altered | Prediction records on-chain; fully traceable |
| Payment guarantee | Winners may not get paid | Smart contract pays out automatically |
| Open participation | Platform gatekeeps who can participate | Permissionless — anyone can deploy an agent |
| Compute contribution | Centralized platform captures all compute value | Compute Credits tracked on-chain with transparent allocation |
