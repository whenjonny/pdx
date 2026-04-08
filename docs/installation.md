# Installation Guide

## Prerequisites

| Tool | Purpose | How to Get |
|------|---------|------------|
| [Foundry](https://getfoundry.sh/) (forge, anvil, cast) | Compile, deploy, and interact with contracts | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| [Node.js](https://nodejs.org/) >= 18 | Build the frontend | https://nodejs.org |
| Python >= 3.10 | Backend and SDK | https://python.org |
| MetaMask (for testnet) | Browser wallet for signing transactions | https://metamask.io |

---

## Quick Start (One-Command Demo)

```bash
./scripts/demo-setup.sh
```

This spins up a local chain, deploys all contracts, creates a sample market, and launches the backend and frontend. Open http://localhost:5173 when it's ready.

---

## Manual Setup (Local Development)

### 1. Start the local chain

```bash
anvil --port 8545 --chain-id 31337 --block-time 1
```

Keep it running. Anvil comes with 10 pre-funded test accounts, each holding 10,000 ETH.

### 2. Deploy contracts

```bash
cd contracts
forge script script/Deploy.s.sol:DeployScript \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --broadcast
```

Note the three addresses printed: MockUSDC, PDXMarket, and PDXOracle.

### 3. Start the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export RPC_URL=http://localhost:8545 CHAIN_ID=31337
export PDX_MARKET_ADDRESS=0x... MOCK_USDC_ADDRESS=0x... PDX_ORACLE_ADDRESS=0x...
export USE_MOCK_MIROFISH=true

uvicorn app.main:app --port 8000 --reload
```

### 4. Start the frontend

```bash
cd frontend
npm install
echo "VITE_CHAIN=local
VITE_PDX_MARKET_ADDRESS=0x...
VITE_MOCK_USDC_ADDRESS=0x..." > .env.local
npm run dev
```

Open http://localhost:5173.

---

## Testnet Deployment (Base Sepolia)

Target network: **Base Sepolia** (Chain ID: 84532)

### Additional Dependencies

| Dependency | Purpose | How to Get |
|------------|---------|------------|
| Alchemy account | RPC endpoint | https://dashboard.alchemy.com |
| Base Sepolia ETH | Gas fees | See the faucet list below |
| Pinata account (optional) | IPFS storage | https://app.pinata.cloud |
| BaseScan API Key (optional) | Contract verification | https://basescan.org/apis |

### Getting Test ETH

| Faucet | URL | Notes |
|--------|-----|-------|
| Alchemy (recommended) | https://www.alchemy.com/faucets/base-sepolia | Free sign-up; also gives you an RPC URL |
| Coinbase CDP | https://portal.cdp.coinbase.com/products/faucet | Coinbase developer portal |
| QuickNode | https://faucet.quicknode.com/base/sepolia | Free sign-up |
| Superchain (OP) | https://app.optimism.io/faucet | Requires GitHub verification |
| Chainlink | https://faucets.chain.link/base-sepolia | Connect MetaMask to claim |
| Bware Labs | https://bwarelabs.com/faucets/base-sepolia | No sign-up required |
| Sepolia → Base bridge | https://testnets.superbridge.app/base-sepolia | Get Sepolia ETH first, then bridge |

> MockUSDC is minted by the contract itself — you do **not** need to get USDC from a faucet.

### Adding Base Sepolia to MetaMask

| Field | Value |
|-------|-------|
| Network Name | Base Sepolia |
| RPC URL | `https://sepolia.base.org` |
| Chain ID | `84532` |
| Currency | ETH |
| Explorer | `https://sepolia.basescan.org` |

### Phase 1: Deploy Contracts

```bash
cd contracts
cp .env.example .env
```

Edit `contracts/.env`:

```bash
PRIVATE_KEY=0xYourMetaMaskPrivateKey
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/YourKey
BASESCAN_API_KEY=YourBasescanKey    # optional
```

Deploy:

```bash
source .env
forge script script/Deploy.s.sol:DeployScript \
  --rpc-url $BASE_SEPOLIA_RPC_URL \
  --broadcast --verify
```

Save the printed addresses, then create a sample market:

```bash
export MOCK_USDC=0xAAAA...
export PDX_MARKET=0xBBBB...
forge script script/CreateMarket.s.sol:CreateMarketScript \
  --rpc-url $BASE_SEPOLIA_RPC_URL --broadcast
```

### Phase 2: Start the Backend

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env`:

```bash
RPC_URL=https://base-sepolia.g.alchemy.com/v2/YourKey
CHAIN_ID=84532
PDX_MARKET_ADDRESS=0xBBBB...
MOCK_USDC_ADDRESS=0xAAAA...
PDX_ORACLE_ADDRESS=0xCCCC...
DEPLOYER_PRIVATE_KEY=0xYourPrivateKey
PINATA_API_KEY=YourPinataKey          # optional
PINATA_SECRET_KEY=YourPinataSecret    # optional
USE_MOCK_MIROFISH=true
```

Launch:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Phase 3: Start the Frontend

```bash
cd frontend
npm install
```

Create `.env.local`:

```bash
VITE_CHAIN=testnet
VITE_RPC_URL=https://base-sepolia.g.alchemy.com/v2/YourKey
VITE_PDX_MARKET_ADDRESS=0xBBBB...
VITE_MOCK_USDC_ADDRESS=0xAAAA...
```

```bash
npm run dev          # development mode
npm run build        # production build → frontend/dist/
```

### Phase 4: Install the OpenClaw Agent Plugin

```bash
cd sdk
pip install -e .
python3 -c "from pdx_sdk.signing import build_buy_url; print('OK')"
```

Set environment variables:

```bash
export PDX_BACKEND_URL="http://localhost:8000"
export PDX_FRONTEND_URL="http://localhost:5173"  # or your Vercel public URL
```

Use it in Claude Code:

```bash
claude --skill ./skill
```

---

## Environment Variable Reference

```bash
# ── contracts/.env ──
PRIVATE_KEY=0x...
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY

# ── backend/.env ──
RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY
CHAIN_ID=84532                         # use 31337 for local
PDX_MARKET_ADDRESS=0x...
MOCK_USDC_ADDRESS=0x...
PDX_ORACLE_ADDRESS=0x...
DEPLOYER_PRIVATE_KEY=0x...             # required for testnet
PINATA_API_KEY=...                     # optional
PINATA_SECRET_KEY=...                  # optional
USE_MOCK_MIROFISH=true                 # set to false for real analysis
MIROFISH_LLM_API_KEY=sk-...           # optional
MIROFISH_LLM_MODEL=gpt-4o-mini
DEPLOY_BLOCK=0                         # block number at contract deployment

# ── frontend/.env.local ──
VITE_CHAIN=testnet                     # local / testnet
VITE_RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY
VITE_PDX_MARKET_ADDRESS=0x...
VITE_MOCK_USDC_ADDRESS=0x...
```

---

## Common Commands

```bash
# Contracts
forge build                    # compile
forge test -vvv                # run unit tests
forge script script/Deploy.s.sol:DeployScript --rpc-url <url> --private-key <key> --broadcast

# Backend
uvicorn app.main:app --port 8000 --reload

# Frontend
npm run dev                    # dev server (port 5173)
npm run build                  # production build

# SDK
pip install -e ./sdk
python sdk/examples/agent_trade.py

# Full stack (one command)
./scripts/demo-setup.sh
```
