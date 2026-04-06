#!/usr/bin/env bash
#
# PDX Demo Setup Script
# Starts anvil local chain, deploys contracts, creates a sample market,
# starts backend and frontend dev servers.
#
# Usage: ./scripts/demo-setup.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[PDX]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }

cleanup() {
  info "Shutting down..."
  [[ -n "${ANVIL_PID:-}" ]] && kill "$ANVIL_PID" 2>/dev/null && echo "  anvil stopped"
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null && echo "  backend stopped"
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null && echo "  frontend stopped"
  exit 0
}
trap cleanup SIGINT SIGTERM

# ─── 1. Check prerequisites ───
info "Checking prerequisites..."
command -v anvil  >/dev/null 2>&1 || { echo "ERROR: anvil not found. Install Foundry: https://getfoundry.sh"; exit 1; }
command -v forge  >/dev/null 2>&1 || { echo "ERROR: forge not found. Install Foundry: https://getfoundry.sh"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found"; exit 1; }
command -v node   >/dev/null 2>&1 || { echo "ERROR: node not found"; exit 1; }
ok "Prerequisites OK"

# ─── 2. Start anvil (local Ethereum chain) ───
info "Starting anvil (local chain) on port 8545..."
anvil --host 0.0.0.0 --port 8545 --chain-id 31337 --block-time 1 &
ANVIL_PID=$!
sleep 2

# Anvil default deployer: account 0
DEPLOYER_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
DEPLOYER_ADDR="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
ok "Anvil running (PID: $ANVIL_PID)"

# ─── 3. Deploy contracts ───
info "Deploying contracts..."
cd "$ROOT/contracts"

DEPLOY_OUTPUT=$(forge script script/Deploy.s.sol:DeployScript \
  --rpc-url http://localhost:8545 \
  --private-key "$DEPLOYER_KEY" \
  --broadcast 2>&1)

# Extract addresses from deploy output
USDC_ADDR=$(echo "$DEPLOY_OUTPUT" | grep -oP 'MockUSDC:\s+\K0x[a-fA-F0-9]+' || true)
MARKET_ADDR=$(echo "$DEPLOY_OUTPUT" | grep -oP 'PDXMarket:\s+\K0x[a-fA-F0-9]+' || true)
ORACLE_ADDR=$(echo "$DEPLOY_OUTPUT" | grep -oP 'PDXOracle:\s+\K0x[a-fA-F0-9]+' || true)

# Fallback: parse from broadcast JSON if grep failed
if [[ -z "$MARKET_ADDR" ]]; then
  warn "Parsing addresses from broadcast artifacts..."
  BROADCAST_DIR="$ROOT/contracts/broadcast/Deploy.s.sol/31337"
  if [[ -d "$BROADCAST_DIR" ]]; then
    LATEST=$(ls -t "$BROADCAST_DIR"/run-*.json 2>/dev/null | head -1)
    if [[ -n "$LATEST" ]]; then
      USDC_ADDR=$(python3 -c "
import json
with open('$LATEST') as f:
    data = json.load(f)
for tx in data.get('transactions', []):
    if tx.get('contractName') == 'MockUSDC':
        print(tx['contractAddress']); break
" 2>/dev/null || true)
      MARKET_ADDR=$(python3 -c "
import json
with open('$LATEST') as f:
    data = json.load(f)
for tx in data.get('transactions', []):
    if tx.get('contractName') == 'PDXMarket':
        print(tx['contractAddress']); break
" 2>/dev/null || true)
      ORACLE_ADDR=$(python3 -c "
import json
with open('$LATEST') as f:
    data = json.load(f)
for tx in data.get('transactions', []):
    if tx.get('contractName') == 'PDXOracle':
        print(tx['contractAddress']); break
" 2>/dev/null || true)
    fi
  fi
fi

if [[ -z "$MARKET_ADDR" ]]; then
  echo "ERROR: Could not extract contract addresses from deployment output"
  echo "$DEPLOY_OUTPUT"
  exit 1
fi

ok "Contracts deployed:"
echo "  MockUSDC:    $USDC_ADDR"
echo "  PDXMarket:   $MARKET_ADDR"
echo "  PDXOracle:   $ORACLE_ADDR"

# ─── 4. Create sample market ───
info "Creating sample market..."
PRIVATE_KEY="$DEPLOYER_KEY" MOCK_USDC="$USDC_ADDR" PDX_MARKET="$MARKET_ADDR" \
  forge script script/CreateMarket.s.sol:CreateMarketScript \
  --rpc-url http://localhost:8545 \
  --private-key "$DEPLOYER_KEY" \
  --broadcast 2>&1 || warn "CreateMarket failed (may already exist)"

ok "Sample market created"
cd "$ROOT"

# ─── 5. Start backend ───
info "Starting backend on port 8000..."
cd "$ROOT/backend"

# Create/activate venv if needed
if [[ ! -d "venv" ]]; then
  python3 -m venv venv
  source venv/bin/activate
  pip install -q -r requirements.txt 2>/dev/null || pip install -q fastapi uvicorn web3 httpx python-dotenv
else
  source venv/bin/activate
fi

# Set backend env
export RPC_URL="http://localhost:8545"
export CHAIN_ID="31337"
export PDX_MARKET_ADDRESS="$MARKET_ADDR"
export MOCK_USDC_ADDRESS="$USDC_ADDR"
export USE_MOCK_MIROFISH="true"

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
sleep 2
ok "Backend running (PID: $BACKEND_PID)"
cd "$ROOT"

# ─── 6. Start frontend ───
info "Starting frontend on port 5173..."
cd "$ROOT/frontend"

# Write .env.local for Vite
cat > .env.local <<EOF
VITE_CHAIN=local
VITE_PDX_MARKET_ADDRESS=$MARKET_ADDR
VITE_MOCK_USDC_ADDRESS=$USDC_ADDR
EOF

npx vite --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!
sleep 2
ok "Frontend running (PID: $FRONTEND_PID)"
cd "$ROOT"

# ─── Done ───
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PDX Demo Environment Ready!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8000"
echo "  API docs:  http://localhost:8000/docs"
echo "  Anvil RPC: http://localhost:8545"
echo ""
echo "  Contract Addresses:"
echo "    MockUSDC:  $USDC_ADDR"
echo "    PDXMarket: $MARKET_ADDR"
echo "    PDXOracle: $ORACLE_ADDR"
echo ""
echo "  Deployer: $DEPLOYER_ADDR"
echo "  (Import into MetaMask with key: ${DEPLOYER_KEY:0:10}...)"
echo ""
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop all services"
echo ""

# Wait for Ctrl+C
wait
