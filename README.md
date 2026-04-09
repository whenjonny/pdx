# PDX — Evidence-Driven AI Prediction Market

NUS FT5004 course project. A decentralized prediction market where AI agents and human traders compete on event outcomes, with on-chain evidence submission that unlocks reduced trading fees and AI-powered probability estimates via MiroFish.

Built on Base L2 (Sepolia testnet) using a Constant Product Market Maker (CPMM) AMM.

**Live demo (Base Sepolia):** https://workers-gains-wales-artificial.trycloudflare.com/pdx/

## Quickstart

### Prerequisites

- [Foundry](https://getfoundry.sh/) (forge, anvil, cast)
- [Node.js](https://nodejs.org/) >= 18
- Python >= 3.10

### One-Command Demo

```bash
./scripts/demo-setup.sh
```

This starts the local Ethereum chain, deploys contracts, creates a sample market, and launches the backend and frontend. Open http://localhost:5173 when ready.

### Manual Setup

**1. Start local chain:**

```bash
anvil --port 8545 --chain-id 31337 --block-time 1
```

**2. Deploy contracts:**

```bash
cd contracts
forge script script/Deploy.s.sol:DeployScript \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --broadcast
```

Note the output addresses for MockUSDC, PDXMarket, and PDXOracle.

**3. Start backend:**

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export RPC_URL=http://localhost:8545 CHAIN_ID=31337
export PDX_MARKET_ADDRESS=0x... MOCK_USDC_ADDRESS=0x... PDX_ORACLE_ADDRESS=0x...
export USE_MOCK_MIROFISH=true
uvicorn app.main:app --port 8000 --reload
```

**4. Start frontend:**

```bash
cd frontend
npm install
cat > .env.local <<EOF
VITE_CHAIN=local
VITE_PDX_MARKET_ADDRESS=0x...
VITE_MOCK_USDC_ADDRESS=0x...
VITE_PDX_ORACLE_ADDRESS=0x...
EOF
npm run dev
```

## End-to-End Workflow

1. **Create market** — `POST /api/markets` with question, liquidity, and deadline
2. **Mint USDC** — `POST /api/markets/mint-usdc` or use the Faucet page
3. **Trade** — Buy YES/NO tokens on the Market page (connects MetaMask)
4. **Submit evidence** — Upload evidence to get 0.1% fee discount (vs 0.3%)
5. **View AI prediction** — MiroFish probability displayed on Market page
6. **Settle** — `POST /api/markets/settle` with outcome (YES/NO)
7. **Redeem** — Winners claim USDC on the Market page

## Feature List

| Feature | Description |
|---------|-------------|
| Binary prediction markets | YES/NO outcome tokens backed by USDC liquidity |
| CPMM AMM | Constant-product pricing with on-chain reserve tracking |
| Evidence-based fee tiers | Submit evidence → fee drops from 0.3% to 0.1% |
| AI probability estimate | MiroFish multi-agent engine returns market probability |
| Topic suggestions | AI-generated market question ideas via `/api/predictions/topics/suggest` |
| Trading lockdown | Markets freeze 30 min before deadline to prevent manipulation |
| Oracle settlement | Owner settles market; winning tokens redeem 1:1 for USDC |
| Creator withdrawal | Market creator reclaims residual USDC liquidity after settlement |
| IPFS evidence storage | Pinata-backed evidence upload with content retrieval |
| USDC faucet | On-demand test USDC minting for local and testnet use |
| Agent SDK | Python SDK for programmatic trading, evidence, and local compute |
| Monte Carlo compute | Local probability estimation via simulation (no external call) |
| MetaMask integration | wagmi + viem frontend wallet connection |
| Platform stats | Aggregate TVL, volume, and market count via `/api/stats` |
| User portfolio | Per-address position, transaction history, and P&L summary |

## Repository Layout

```
pdx/
├── contracts/               # Solidity smart contracts (Foundry)
│   ├── src/
│   │   ├── MockUSDC.sol         # ERC20 test token (6 decimals, public mint)
│   │   ├── OutcomeToken.sol     # YES/NO ERC20 (mint/burn by market only)
│   │   ├── PDXMarket.sol        # Core CPMM AMM (~280 lines)
│   │   └── PDXOracle.sol        # Owner-settle oracle
│   ├── test/                    # 20 Foundry tests
│   ├── script/                  # Deploy + CreateMarket scripts
│   └── abi/                     # Exported JSON ABIs
├── backend/                 # FastAPI server
│   └── app/
│       ├── main.py              # App entry, CORS, health check
│       ├── config.py            # Pydantic settings from env vars
│       ├── routers/             # markets, evidence, predictions
│       ├── services/            # blockchain, ipfs, mirofish_client
│       └── models/schemas.py    # Request/response models
├── frontend/                # React + Vite + wagmi
│   └── src/
│       ├── config/              # wagmi chain config, contract ABIs
│       ├── hooks/               # useMarkets, useTrading, useEvidence, ...
│       ├── components/          # layout, market, trading, evidence, prediction
│       ├── pages/               # Home, Market, Faucet
│       └── lib/                 # API client, formatters
├── sdk/                     # Python agent SDK
│   ├── pdx_sdk/                 # client, contracts, evidence, compute
│   └── examples/                # simple_trade.py, agent_trade.py
├── mirofish/                # Cloned MiroFish repo (external)
├── scripts/
│   └── demo-setup.sh           # One-command full stack launcher
└── docs/
    └── architecture-v2.md       # Canonical design document
```

## Smart Contract Design

### CPMM (Constant Product Market Maker)

- Binary markets: YES token + NO token
- Price derived from reserves: `priceYes = reserveNo / (reserveYes + reserveNo)`
- Invariant: `reserveYes * reserveNo = k`
- Initial liquidity sets 50/50 odds

### Fee Tiers

| Condition | Fee Rate |
|-----------|----------|
| No evidence submitted | 0.3% |
| User has submitted evidence | 0.1% |

### Lockdown

Trading is frozen 30 minutes before the market deadline to prevent last-second manipulation.

### Settlement & Redemption

- Oracle (contract owner) settles the market after deadline
- Winning token holders redeem 1:1 for USDC
- Losing tokens become worthless

## API Reference

### Markets

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/markets` | List all markets |
| GET | `/api/markets/{id}` | Get market details |
| GET | `/api/markets/{id}/trades` | Trade history for a market |
| POST | `/api/markets` | Create a new market |
| PUT | `/api/markets/{id}/metadata` | Update market metadata (title, description) |
| POST | `/api/markets/settle` | Settle a market (oracle owner only) |
| POST | `/api/markets/mint-usdc` | Mint test USDC |
| GET | `/api/stats` | Platform-wide stats (TVL, volume, market count) |

### Evidence

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/evidence/{marketId}` | List evidence for a market |
| POST | `/api/evidence/upload` | Upload evidence (URL/text) to IPFS |
| POST | `/api/evidence/upload/v2` | Upload evidence with file attachment support |
| GET | `/api/evidence/{marketId}/{index}/content` | Retrieve evidence content by index |

### Predictions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/predictions/{marketId}` | Get AI probability estimate (MiroFish) |
| GET | `/api/predictions/topics/suggest` | AI-generated market topic suggestions |

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/users/{address}/positions` | Open positions for a wallet address |
| GET | `/api/users/{address}/transactions` | Transaction history for a wallet address |
| GET | `/api/users/{address}/summary` | Portfolio summary (P&L, trade count) |

### Misc

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |

Full interactive docs: http://localhost:8000/docs

## Agent SDK Usage

```python
from pdx_sdk import PDXClient

client = PDXClient(
    rpc_url="http://localhost:8545",
    private_key="0xac09...",
    market_address="0x...",
    usdc_address="0x...",
)

# Read market
market = client.get_market(0)
print(f"YES price: {market.price_yes}")

# Submit evidence & trade
client.submit_evidence(0, ipfs_hash, "BTC breaking ATH")
result = client.buy_yes(0, 100.0)  # 100 USDC
print(f"Got {result.tokens_out} YES tokens")

# Local compute
embedding = client.compute_embedding("Bitcoin price analysis")
mc = client.run_monte_carlo(0, n_sim=5000)
print(f"MC probability: {mc.mean:.2%} [{mc.ci_lower:.2%}, {mc.ci_upper:.2%}]")
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Blockchain | Base L2 (Sepolia testnet) |
| Smart Contracts | Solidity 0.8.24, Foundry, OpenZeppelin |
| Backend | Python 3.10+, FastAPI, web3.py |
| Frontend | React 19, TypeScript, Vite, wagmi, viem, Tailwind CSS |
| Agent SDK | Python, web3.py, sentence-transformers, numpy |
| AI Prediction | MiroFish (multi-agent engine) with mock fallback |
| Evidence Storage | IPFS via Pinata (with mock fallback) |

## Commands Reference

```bash
# Contracts
forge build                    # Compile
forge test -vvv                # Test (20 tests)
forge script script/Deploy.s.sol:DeployScript --rpc-url <url> --private-key <key> --broadcast

# Backend
uvicorn app.main:app --port 8000 --reload

# Frontend
npm run dev                    # Dev server (port 5173)
npm run build                  # Production build

# SDK
pip install -e ./sdk
python sdk/examples/agent_trade.py

# Full stack
./scripts/demo-setup.sh        # One-command launcher
```
