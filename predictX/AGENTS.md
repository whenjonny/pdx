# Repository Guidelines

## Project Structure & Module Organization

This is a monorepo with four independent modules that compose into a full-stack prediction market platform:

- `contracts/` — Solidity smart contracts (Foundry/Forge). Core AMM logic lives in `PDXMarket.sol`. Tests in `contracts/test/`, deploy scripts in `contracts/script/`, exported ABIs in `contracts/abi/`.
- `backend/` — FastAPI server (`backend/app/`). Read-only blockchain queries plus write endpoints (create market, mint USDC, settle). MiroFish integration with mock fallback.
- `frontend/` — React + TypeScript + Vite (`frontend/src/`). Uses wagmi/viem for on-chain interaction, Tailwind CSS for styling, React Router for navigation.
- `sdk/` — Python agent SDK (`sdk/pdx_sdk/`). Programmatic market interaction, evidence submission, and local compute (embeddings + Monte Carlo).
- `mirofish/` — Cloned upstream MiroFish repo (multi-agent prediction engine). Do not modify files here; treat as external dependency.
- `docs/` — Architecture design documents. `architecture-v2.md` is the canonical reference.
- `scripts/` — Automation scripts. `demo-setup.sh` starts the full local stack.

When extending, keep each module self-contained. Cross-module references should go through ABIs (contracts→backend/frontend), HTTP APIs (backend→frontend/sdk), or environment variables.

## Build, Test, and Development Commands

### Contracts (Foundry)

```bash
cd contracts
forge build              # compile all contracts
forge test -vvv          # run all 20 tests with verbose output
forge fmt                # format Solidity code
```

Key config: `foundry.toml` requires `via_ir = true` (Market struct has 14 fields).

### Backend (Python / FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Required environment variables:
- `RPC_URL` — Ethereum RPC endpoint (default: `http://localhost:8545`)
- `CHAIN_ID` — Chain ID (31337 for anvil, 84532 for Base Sepolia)
- `PDX_MARKET_ADDRESS` — Deployed PDXMarket contract address
- `MOCK_USDC_ADDRESS` — Deployed MockUSDC contract address
- `PDX_ORACLE_ADDRESS` — Deployed PDXOracle contract address (optional)
- `USE_MOCK_MIROFISH` — `true` to use mock predictions (default: `true`)

### Frontend (React / Vite)

```bash
cd frontend
npm install
npm run dev              # dev server on port 5173
npm run build            # production build
```

Env vars via `.env.local`:
- `VITE_CHAIN` — `local` for anvil, omit for Base Sepolia
- `VITE_PDX_MARKET_ADDRESS`, `VITE_MOCK_USDC_ADDRESS` — contract addresses

### SDK (Python)

```bash
cd sdk
pip install -e .
python examples/simple_trade.py
```

### Full Stack (One Command)

```bash
./scripts/demo-setup.sh
```

Starts anvil → deploys contracts → creates sample market → starts backend → starts frontend.

## Coding Style & Naming Conventions

### Solidity

- Solidity 0.8.24, optimizer enabled (200 runs), `via_ir = true`
- OpenZeppelin imports via `@openzeppelin/contracts/`
- Custom errors over require strings: `error OnlyMarket();`
- Constants: `UPPER_CASE` (e.g., `FEE_NORMAL`, `LOCKDOWN_BUFFER`)
- Functions: `camelCase` (e.g., `createMarket`, `submitEvidence`)
- Events: `PastTense` (e.g., `MarketCreated`, `Trade`, `EvidenceSubmitted`)

### Python (Backend & SDK)

- Python 3.10+, `snake_case` for functions and variables
- Pydantic models for API schemas (backend) and dataclasses for SDK types
- Type hints on all public functions
- FastAPI routers under `app/routers/`, services under `app/services/`

### TypeScript (Frontend)

- React functional components with hooks
- Files: `PascalCase.tsx` for components, `camelCase.ts` for hooks/utils
- Hooks prefix: `use` (e.g., `useMarkets`, `useTrading`)
- Tailwind CSS classes inline, no separate CSS files
- wagmi hooks for on-chain reads/writes (`useReadContract`, `useWriteContract`)

## Testing Guidelines

### Contracts

Run `forge test -vvv` before any contract changes. All 20 tests must pass. Tests cover:

- Market lifecycle (create → trade → evidence → settle → redeem)
- CPMM math (price movement, reserve invariants)
- Fee tiers (0.3% normal, 0.1% with evidence)
- Lockdown mechanism (30 min before deadline)
- Access control (oracle-only settle, market-only mint/burn)

### Backend

No automated test suite yet. Verify manually:
- `curl http://localhost:8000/api/health` returns `{"status":"ok",...}`
- `curl http://localhost:8000/api/markets` returns market list
- Swagger UI at `http://localhost:8000/docs` for interactive testing

### Frontend

Run `npm run build` to verify TypeScript compilation and bundling. No unit tests yet — verify flows manually in browser.

## Deployment

### Local (Anvil)

Use `./scripts/demo-setup.sh` or manually:

1. `anvil --port 8545 --chain-id 31337 --block-time 1`
2. Deploy: `forge script script/Deploy.s.sol:DeployScript --rpc-url http://localhost:8545 --private-key 0xac09...ff80 --broadcast`
3. Note contract addresses from deploy output
4. Start backend and frontend with those addresses

Anvil account 0 private key: `0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80`

### Testnet (Base Sepolia)

See `contracts/DEPLOY_GUIDE.md` for step-by-step instructions. Requires:
- MetaMask with Base Sepolia network
- Test ETH from faucet (Alchemy or Superchain)
- Alchemy RPC URL

## Security & Configuration Tips

- Never commit private keys or `.env` files. Use `.env.example` as template.
- The `deployer_private_key` in backend config defaults to anvil account 0 — safe for local dev only. Remove or change for any non-local deployment.
- Contract ABIs are exported to `contracts/abi/` and imported by backend, frontend, and SDK. Regenerate after contract changes: `jq '.abi' contracts/out/X.sol/X.json > contracts/abi/X.json`.
- MockUSDC has a public `mint()` — this is intentional for testnet. Never deploy to mainnet.

## Key Architecture Decisions

| Area | Decision | Rationale |
|------|----------|-----------|
| AMM | CPMM (x*y=k) | Simple, well-understood, sufficient for binary markets |
| Oracle | Owner-settle (PDXOracle) | MVP simplicity; interface ready for Chainlink upgrade |
| Fee tiers | 0.3% / 0.1% | Evidence submission incentive; 0.1% unlocked per-user |
| Lockdown | deadline - 30 min | Prevents last-second manipulation |
| Token decimals | 6 (matching USDC) | 1:1 redemption math, no conversion needed |
| MiroFish | Mock client default | Real integration is stretch goal; mock uses AMM price + noise |
| Frontend state | wagmi + react-query | Standard Web3 React stack; auto-refetch for live data |
