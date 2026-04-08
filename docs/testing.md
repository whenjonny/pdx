# Testing Guide

This document covers the full end-to-end testing flow for both local (Anvil) and Base Sepolia testnet environments.

---

## 1. Local E2E Testing (Anvil)

No MetaMask or browser needed — everything runs from the command line.

### Prerequisites

| Tool | Install |
|------|---------|
| Foundry (anvil, forge, cast) | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| Python >= 3.10 | https://python.org |
| Node.js >= 18 | https://nodejs.org |
| jq (optional) | `brew install jq` |

### Step 0: Start the Environment

Open **3 terminal windows**:

**Terminal 1 — Local chain (Anvil):**

```bash
anvil --port 8545 --chain-id 31337 --block-time 1
```

**Terminal 2 — Deploy contracts:**

```bash
cd contracts
forge script script/Deploy.s.sol:DeployScript \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --broadcast
```

Note the three addresses and export them:

```bash
export USDC=0x5FbDB2315678afecb367f032d93F642f64180aa3
export MARKET=0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
export ORACLE=0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0
```

**Terminal 3 — Start the backend:**

```bash
cd backend && source .venv/bin/activate
export RPC_URL=http://localhost:8545 CHAIN_ID=31337
export PDX_MARKET_ADDRESS=$MARKET MOCK_USDC_ADDRESS=$USDC PDX_ORACLE_ADDRESS=$ORACLE
export USE_MOCK_MIROFISH=true
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 1: Health Check

```bash
curl -s http://localhost:8000/api/health | jq
# Expected: {"status":"ok","chain_connected":true}
```

### Step 2: Create a Market

```bash
curl -s -X POST http://localhost:8000/api/markets \
  -H "Content-Type: application/json" \
  -d '{"question":"Will BTC exceed $100K by June 2026?","initial_liquidity":10000,"deadline_days":30}' | jq
# Expected: market_id=0, initial_liquidity=10000000000
```

### Step 3: List Markets

```bash
curl -s http://localhost:8000/api/markets | jq
# Verify: priceYes ≈ 0.5, priceNo ≈ 0.5, resolved=false
```

### Step 4: Check AI Prediction

```bash
curl -s http://localhost:8000/api/predictions/0 | jq
# Expected: probability_yes ≈ 0.5, source="MiroFish Mock"
```

### Step 5: On-Chain Trading

```bash
# Anvil test accounts
TRADER_A_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
TRADER_A=0x70997970C51812dc3A010C7d01b50e0d17dc79C8

# Mint USDC
cast send $USDC "mint(address,uint256)" $TRADER_A 50000000000 \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

# Approve
cast send $USDC "approve(address,uint256)" $MARKET $(cast max-uint) \
  --rpc-url http://localhost:8545 --private-key $TRADER_A_KEY

# Buy YES: 1,000 USDC
cast send $MARKET "buyYes(uint256,uint256)" 0 1000000000 \
  --rpc-url http://localhost:8545 --private-key $TRADER_A_KEY

# Verify price change
cast call $MARKET "getPriceYes(uint256)(uint256)" 0 --rpc-url http://localhost:8545
# Expected: > 500000 (i.e. > $0.50)
```

### Step 6: Submit Evidence

```bash
# Upload to IPFS (mock mode)
curl -s -X POST http://localhost:8000/api/evidence/upload \
  -H "Content-Type: application/json" \
  -d '{"market_id":0,"title":"BTC Analysis","content":"Based on halving cycles, BTC likely exceeds 100K.","source_url":"https://example.com","direction":"YES"}' | jq

# Submit on-chain (use the ipfs_hash returned above)
cast send $MARKET "submitEvidence(uint256,bytes32,string)" \
  0 0x<hash> "BTC halving cycle analysis" \
  --rpc-url http://localhost:8545 --private-key $TRADER_A_KEY

# Verify
curl -s http://localhost:8000/api/evidence/0 | jq
```

### Step 7: Frontend Build Check

```bash
cd frontend
echo "VITE_CHAIN=local
VITE_PDX_MARKET_ADDRESS=$MARKET
VITE_MOCK_USDC_ADDRESS=$USDC" > .env.local
npm run build
# Expected: dist/index.html generated successfully
```

---

## 2. Settlement Testing (Anvil)

Run the automated settlement script to test the full settle-and-redeem flow:

```bash
cd e2e
bash test-settle.sh
```

The script runs 8 steps automatically:
1. Deploy contracts
2. Create a market (2-minute deadline)
3. Buy YES tokens
4. Fast-forward time past the deadline
5. Oracle settles the market (YES wins)
6. Redeem USDC
7. Verify that tokens were burned
8. Verify that USDC balance increased

---

## 3. Testnet E2E Testing (Base Sepolia)

### Automated Test

```bash
cd e2e
bash testnet-deploy.sh          # full flow
bash testnet-deploy.sh --skip-deploy  # skip deployment if contracts are already live
```

### Eight Test Phases

```
Phase 1: Prerequisites Check
  ├── Verify toolchain (forge, cast, python3, node)
  ├── Load contracts/.env
  └── Confirm deployer has ETH

Phase 2: Contract Deployment
  ├── Run forge test (unit tests first)
  ├── forge script Deploy.s.sol → Base Sepolia
  └── Extract contract addresses

Phase 3: On-Chain Verification
  ├── MockUSDC / PDXMarket / Oracle respond to calls
  └── Check deployer USDC balance

Phase 4: Create Sample Market
  ├── Create a sample market
  └── Verify YES price > 0

Phase 5: Trading Test (Buy YES)
  ├── Approve USDC → PDXMarket
  ├── buyYes(0, 100 USDC)
  └── Verify price increased (AMM is working)

Phase 6: Backend API Test
  ├── GET /api/health, /api/markets
  ├── POST /api/evidence/upload → cast submitEvidence
  ├── GET /api/predictions/0 (MiroFish)
  └── buyYes after evidence (0.1% fee tier)

Phase 7: Frontend Build Test
  ├── Configure .env.local (testnet mode)
  └── npm run build

Phase 8: Sell Test
  ├── Sell back half of YES tokens
  └── Verify price decreased
```

### End-to-End Verification (Agent Flow)

```
1. Agent: /pdx-markets          → list active markets
2. Agent: /pdx-analyze 1        → web search + embedding + Monte Carlo
3. Agent: /pdx-submit 1 --direction YES  → IPFS upload + signing URL
4. User clicks link              → MetaMask signs → evidence recorded on-chain
5. Agent: /pdx-trade 1 --amount 100      → trade signing URL
6. User clicks link              → MetaMask confirms → YES tokens received
```

### Expected Output

```
[OK]  All tools available (forge, cast, python3, node)
[OK]  Contracts deployed!
[OK]  MockUSDC contract responds
[OK]  PDXMarket contract responds
[OK]  Market 0 has a question
[OK]  YES price increased after buy (AMM working)
[OK]  Backend health check passed
[OK]  Backend returns 1 market(s)
[OK]  Prediction returned (prob_yes=0.52, source=MiroFish Mock)
[OK]  Evidence uploaded (CID=Qm...)
[OK]  Evidence submitted on-chain
[OK]  Frontend build succeeded
[OK]  YES price decreased after sell (AMM working)

  Passed: 21 / Failed: 0
```

---

## 4. Data Flow

```
User submits evidence
    ├─→ POST /api/evidence/upload → IPFS pin → CID + bytes32 hash
    ├─→ cast submitEvidence(marketId, bytes32, summary) → stored on-chain
    └─→ hasEvidence[user] = true → next trade charged 0.1% fee

MiroFish scheduled analysis (every 5 minutes)
    ├─→ blockchain_service.list_markets() → active markets
    ├─→ blockchain_service.get_evidence_list() → on-chain evidence
    ├─→ ipfs_service.fetch_by_hash() → full evidence content from IPFS
    └─→ analyze_market() → LLM / heuristic → probability

Frontend display
    ├─→ AMM price → "Market Price" (real trading price)
    └─→ MiroFish → "AI Reference" (advisory only)
```

---

## 5. Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `insufficient funds` | Not enough test ETH | Get ETH from a faucet (see [Installation Guide](./installation.md)) |
| `could not connect` | Wrong RPC URL | Check that Alchemy / Anvil is running |
| `nonce too low` | Previous transaction still pending | Wait a few seconds and retry |
| Backend 504 | RPC rate limit | Switch RPC provider or wait briefly |
| Price unchanged after trade | Transaction may not have landed | Check the tx hash on BaseScan |
| IPFS content 404 | CID was in memory and lost on restart | Re-upload evidence or configure Pinata |
| `chain_connected: false` | Anvil is not running | Start Anvil |
| Frontend blank page | Contract addresses not configured | Check `.env.local` |
| MetaMask doesn't pop up | Wrong network selected | Switch MetaMask to Base Sepolia |
| `sentence-transformers` install slow | Large model download | Try `pip install --no-deps` then install dependencies manually |

---

## 6. Manual Browser Verification

After deployment, you can also verify directly from a browser:

1. Go to https://sepolia.basescan.org
2. Search for the PDXMarket address
3. Contract → Read Contract → `getPriceYes(0)` to check the current price
4. Contract → Write Contract → connect MetaMask and submit transactions
