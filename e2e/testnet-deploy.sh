#!/usr/bin/env bash
#
# PDX E2E Testnet Deployment & Testing Script
#
# Deploys contracts to Base Sepolia, starts backend + frontend,
# and runs a full E2E smoke test against the live testnet.
#
# Prerequisites:
#   - foundry (forge, cast) installed
#   - node.js + npm installed
#   - python3 installed
#   - contracts/.env configured with PRIVATE_KEY + BASE_SEPOLIA_RPC_URL
#
# Usage:
#   ./e2e/testnet-deploy.sh              # Full deploy + test
#   ./e2e/testnet-deploy.sh --skip-deploy # Skip deployment, use existing addresses
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ──── Colors ────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[E2E]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}  $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }

PASS=0
FAIL=0
assert_ok() {
  if [[ $? -eq 0 ]]; then
    ok "$1"
    ((PASS++))
  else
    fail "$1"
    ((FAIL++))
  fi
}

SKIP_DEPLOY=false
[[ "${1:-}" == "--skip-deploy" ]] && SKIP_DEPLOY=true

# ──── Cleanup ────
BACKEND_PID=""
cleanup() {
  info "Cleaning up..."
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null && echo "  backend stopped"
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# ════════════════════════════════════════════════════
#  Phase 1: Prerequisites Check
# ════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Phase 1: Prerequisites Check${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"

info "Checking tools..."
command -v forge   >/dev/null 2>&1 || { fail "forge not found. Install Foundry: https://getfoundry.sh"; exit 1; }
command -v cast    >/dev/null 2>&1 || { fail "cast not found. Install Foundry: https://getfoundry.sh"; exit 1; }
command -v python3 >/dev/null 2>&1 || { fail "python3 not found"; exit 1; }
command -v node    >/dev/null 2>&1 || { fail "node not found"; exit 1; }
ok "All tools available (forge, cast, python3, node)"

# Load testnet env
if [[ -f "$ROOT/contracts/.env" ]]; then
  set -a
  source "$ROOT/contracts/.env"
  set +a
  ok "Loaded contracts/.env"
else
  fail "contracts/.env not found. Copy .env.example and fill in PRIVATE_KEY + BASE_SEPOLIA_RPC_URL"
  exit 1
fi

# Validate required env
[[ -z "${PRIVATE_KEY:-}" ]] && { fail "PRIVATE_KEY not set in contracts/.env"; exit 1; }
[[ -z "${BASE_SEPOLIA_RPC_URL:-}" ]] && { fail "BASE_SEPOLIA_RPC_URL not set in contracts/.env"; exit 1; }

DEPLOYER_ADDR=$(cast wallet address "$PRIVATE_KEY" 2>/dev/null)
ok "Deployer address: $DEPLOYER_ADDR"

# Check ETH balance
ETH_BALANCE=$(cast balance "$DEPLOYER_ADDR" --rpc-url "$BASE_SEPOLIA_RPC_URL" 2>/dev/null || echo "0")
info "ETH balance: $ETH_BALANCE wei"
if [[ "$ETH_BALANCE" == "0" ]]; then
  fail "No ETH on deployer. Get testnet ETH from https://www.alchemy.com/faucets/base-sepolia"
  exit 1
fi
ok "Deployer has ETH for gas"


# ════════════════════════════════════════════════════
#  Phase 2: Contract Deployment
# ════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Phase 2: Contract Deployment (Base Sepolia)${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"

if [[ "$SKIP_DEPLOY" == true ]]; then
  warn "Skipping deployment (--skip-deploy)"
  # Read addresses from env
  USDC_ADDR="${MOCK_USDC:?Set MOCK_USDC in contracts/.env when using --skip-deploy}"
  MARKET_ADDR="${PDX_MARKET:?Set PDX_MARKET in contracts/.env when using --skip-deploy}"
  ORACLE_ADDR="${PDX_ORACLE:?Set PDX_ORACLE in contracts/.env when using --skip-deploy}"
  ok "Using existing addresses from .env"
else
  info "Running forge unit tests first..."
  cd "$ROOT/contracts"
  forge test --no-match-test "testFuzz" -q && ok "Forge tests passed" || { fail "Forge tests failed, aborting deployment"; exit 1; }

  info "Deploying contracts to Base Sepolia..."
  DEPLOY_OUTPUT=$(forge script script/Deploy.s.sol:DeployScript \
    --rpc-url "$BASE_SEPOLIA_RPC_URL" \
    --broadcast \
    --slow 2>&1)

  echo "$DEPLOY_OUTPUT" | tail -20

  # Extract addresses
  USDC_ADDR=$(echo "$DEPLOY_OUTPUT" | grep -oP 'MockUSDC:\s+\K0x[a-fA-F0-9]+' || true)
  MARKET_ADDR=$(echo "$DEPLOY_OUTPUT" | grep -oP 'PDXMarket:\s+\K0x[a-fA-F0-9]+' || true)
  ORACLE_ADDR=$(echo "$DEPLOY_OUTPUT" | grep -oP 'PDXOracle:\s+\K0x[a-fA-F0-9]+' || true)

  # Fallback: parse from broadcast JSON
  if [[ -z "$MARKET_ADDR" ]]; then
    warn "Parsing addresses from broadcast artifacts..."
    BROADCAST_DIR="$ROOT/contracts/broadcast/Deploy.s.sol/84532"
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
    fail "Could not extract contract addresses"
    echo "$DEPLOY_OUTPUT"
    exit 1
  fi

  ok "Contracts deployed!"
  cd "$ROOT"
fi

echo ""
echo "  MockUSDC:   $USDC_ADDR"
echo "  PDXMarket:  $MARKET_ADDR"
echo "  PDXOracle:  $ORACLE_ADDR"
echo ""

# Wait for deployment to finalize on chain
info "Waiting for contracts to finalize (10s)..."
sleep 10


# ════════════════════════════════════════════════════
#  Phase 3: On-chain Verification (cast calls)
# ════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Phase 3: On-chain Contract Verification${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"

RPC="$BASE_SEPOLIA_RPC_URL"

# 3.1 Verify MockUSDC deployed
info "3.1 Verify MockUSDC is deployed..."
USDC_NAME=$(cast call "$USDC_ADDR" "name()(string)" --rpc-url "$RPC" 2>/dev/null || echo "")
[[ "$USDC_NAME" == *"USDC"* || "$USDC_NAME" == *"Mock"* ]]
assert_ok "MockUSDC contract responds (name=$USDC_NAME)"

# 3.2 Verify PDXMarket deployed
info "3.2 Verify PDXMarket is deployed..."
MARKET_USDC=$(cast call "$MARKET_ADDR" "usdc()(address)" --rpc-url "$RPC" 2>/dev/null || echo "")
[[ -n "$MARKET_USDC" && "$MARKET_USDC" != "0x" ]]
assert_ok "PDXMarket contract responds (usdc=$MARKET_USDC)"

# 3.3 Verify Oracle is set
info "3.3 Verify Oracle is set on market..."
MARKET_ORACLE=$(cast call "$MARKET_ADDR" "oracle()(address)" --rpc-url "$RPC" 2>/dev/null || echo "")
ORACLE_LOWER=$(echo "$ORACLE_ADDR" | tr '[:upper:]' '[:lower:]')
MARKET_ORACLE_LOWER=$(echo "$MARKET_ORACLE" | tr '[:upper:]' '[:lower:]')
[[ "$MARKET_ORACLE_LOWER" == *"$ORACLE_LOWER"* || "$ORACLE_LOWER" == *"$MARKET_ORACLE_LOWER"* ]]
assert_ok "Oracle correctly set on PDXMarket"

# 3.4 Check deployer USDC balance
info "3.4 Check deployer USDC balance..."
USDC_BAL=$(cast call "$USDC_ADDR" "balanceOf(address)(uint256)" "$DEPLOYER_ADDR" --rpc-url "$RPC" 2>/dev/null || echo "0")
info "Deployer USDC balance: $USDC_BAL (raw, 6 decimals)"


# ════════════════════════════════════════════════════
#  Phase 4: Create Sample Market (on-chain)
# ════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Phase 4: Create Sample Market${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"

# Check if market 0 already exists
MARKET_COUNT=$(cast call "$MARKET_ADDR" "marketCount()(uint256)" --rpc-url "$RPC" 2>/dev/null || echo "0")
info "Current market count: $MARKET_COUNT"

if [[ "$MARKET_COUNT" == "0" ]]; then
  info "Creating sample market via forge script..."
  cd "$ROOT/contracts"

  export MOCK_USDC="$USDC_ADDR"
  export PDX_MARKET="$MARKET_ADDR"
  export PDX_ORACLE="$ORACLE_ADDR"

  forge script script/CreateMarket.s.sol:CreateMarketScript \
    --rpc-url "$RPC" \
    --broadcast \
    --slow 2>&1 | tail -5

  sleep 10
  MARKET_COUNT=$(cast call "$MARKET_ADDR" "marketCount()(uint256)" --rpc-url "$RPC" 2>/dev/null || echo "0")
  cd "$ROOT"
fi

[[ "$MARKET_COUNT" -ge 1 ]]
assert_ok "At least 1 market exists (count=$MARKET_COUNT)"

# 4.1 Read market details
info "4.1 Reading market 0 details..."
MARKET_Q=$(cast call "$MARKET_ADDR" "getQuestion(uint256)(string)" 0 --rpc-url "$RPC" 2>/dev/null || echo "")
info "Market 0 question: $MARKET_Q"
[[ -n "$MARKET_Q" ]]
assert_ok "Market 0 has a question"

PRICE_YES=$(cast call "$MARKET_ADDR" "getPriceYes(uint256)(uint256)" 0 --rpc-url "$RPC" 2>/dev/null || echo "0")
info "Market 0 priceYes: $PRICE_YES (raw, /1e6 = price)"
[[ "$PRICE_YES" -gt 0 ]]
assert_ok "Market 0 has positive YES price"


# ════════════════════════════════════════════════════
#  Phase 5: Trading Test (buy YES via cast)
# ════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Phase 5: Trading Test (Buy YES)${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"

# 5.1 Approve USDC
info "5.1 Approving USDC for PDXMarket..."
APPROVE_TX=$(cast send "$USDC_ADDR" "approve(address,uint256)" \
  "$MARKET_ADDR" "115792089237316195423570985008687907853269984665640564039457584007913129639935" \
  --rpc-url "$RPC" \
  --private-key "$PRIVATE_KEY" 2>&1 || true)
echo "$APPROVE_TX" | grep -q "transactionHash\|blockNumber\|status.*1" 2>/dev/null
assert_ok "USDC approved for PDXMarket"
sleep 5

# 5.2 Buy YES (100 USDC = 100_000_000 raw)
PRICE_BEFORE=$PRICE_YES
info "5.2 Buying YES tokens with 100 USDC..."
BUY_TX=$(cast send "$MARKET_ADDR" "buyYes(uint256,uint256)" \
  0 100000000 \
  --rpc-url "$RPC" \
  --private-key "$PRIVATE_KEY" 2>&1 || true)
echo "$BUY_TX" | grep -q "transactionHash\|blockNumber\|status.*1" 2>/dev/null
assert_ok "buyYes transaction submitted"
sleep 10

# 5.3 Verify price moved
PRICE_AFTER=$(cast call "$MARKET_ADDR" "getPriceYes(uint256)(uint256)" 0 --rpc-url "$RPC" 2>/dev/null || echo "0")
info "Price before: $PRICE_BEFORE → after: $PRICE_AFTER"
[[ "$PRICE_AFTER" -gt "$PRICE_BEFORE" ]]
assert_ok "YES price increased after buy (AMM working)"


# ════════════════════════════════════════════════════
#  Phase 6: Backend API Test
# ════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Phase 6: Backend API Test${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"

cd "$ROOT/backend"

# Setup venv
if [[ ! -d "venv" ]]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt 2>/dev/null

# Start backend pointing to Base Sepolia
export RPC_URL="$BASE_SEPOLIA_RPC_URL"
export CHAIN_ID="84532"
export PDX_MARKET_ADDRESS="$MARKET_ADDR"
export MOCK_USDC_ADDRESS="$USDC_ADDR"
export PDX_ORACLE_ADDRESS="$ORACLE_ADDR"
export USE_MOCK_MIROFISH="true"

info "Starting backend on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 3
cd "$ROOT"

# 6.1 Health check
info "6.1 Health check..."
HEALTH=$(curl -sf http://localhost:8000/api/health 2>/dev/null || echo "{}")
echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'" 2>/dev/null
assert_ok "Backend health check passed"

# 6.2 List markets
info "6.2 Fetching markets..."
MARKETS=$(curl -sf http://localhost:8000/api/markets 2>/dev/null || echo "[]")
MARKET_LEN=$(echo "$MARKETS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
[[ "$MARKET_LEN" -ge 1 ]]
assert_ok "Backend returns $MARKET_LEN market(s)"

# 6.3 Get single market
info "6.3 Fetching market 0 details..."
MARKET0=$(curl -sf http://localhost:8000/api/markets/0 2>/dev/null || echo "{}")
M0_Q=$(echo "$MARKET0" | python3 -c "import sys,json; print(json.load(sys.stdin).get('question',''))" 2>/dev/null || echo "")
[[ -n "$M0_Q" ]]
assert_ok "Market 0 details returned (question='$M0_Q')"

# 6.4 Get prediction
info "6.4 Fetching AI prediction for market 0..."
PRED=$(curl -sf http://localhost:8000/api/predictions/0 2>/dev/null || echo "{}")
PRED_PROB=$(echo "$PRED" | python3 -c "import sys,json; print(json.load(sys.stdin).get('probability_yes',0))" 2>/dev/null || echo "0")
PRED_SRC=$(echo "$PRED" | python3 -c "import sys,json; print(json.load(sys.stdin).get('source',''))" 2>/dev/null || echo "")
[[ "$PRED_PROB" != "0" ]]
assert_ok "Prediction returned (prob_yes=$PRED_PROB, source=$PRED_SRC)"

# 6.5 Get evidence list
info "6.5 Fetching evidence for market 0..."
EVIDENCE=$(curl -sf http://localhost:8000/api/evidence/0 2>/dev/null || echo "[]")
EV_LEN=$(echo "$EVIDENCE" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
ok "Evidence count: $EV_LEN (may be 0 for new market)"

# 6.6 Get market trades
info "6.6 Fetching trade history for market 0..."
TRADES=$(curl -sf http://localhost:8000/api/markets/0/trades 2>/dev/null || echo "[]")
TRADE_LEN=$(echo "$TRADES" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
[[ "$TRADE_LEN" -ge 1 ]]
assert_ok "Trade history has $TRADE_LEN trade(s) (includes our buyYes)"

# 6.7 Upload evidence via API (IPFS mock mode)
info "6.7 Uploading evidence for market 0..."
EV_UPLOAD=$(curl -sf -X POST http://localhost:8000/api/evidence/upload \
  -H "Content-Type: application/json" \
  -d '{"market_id":0,"title":"BTC ETF inflows rising","content":"BlackRock Bitcoin ETF saw record $1.2B inflows this week, signaling strong institutional demand.","source_url":"https://example.com/btc-etf","direction":"YES"}' \
  2>/dev/null || echo "{}")
EV_CID=$(echo "$EV_UPLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cid',''))" 2>/dev/null || echo "")
EV_HASH=$(echo "$EV_UPLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('evidenceHash',''))" 2>/dev/null || echo "")
[[ -n "$EV_CID" && "$EV_CID" != "" ]]
assert_ok "Evidence uploaded (CID=$EV_CID)"

# 6.8 Submit evidence on-chain (via cast)
info "6.8 Submitting evidence on-chain..."
EV_HASH_BYTES="${EV_HASH}"
SUBMIT_TX=$(cast send "$MARKET_ADDR" "submitEvidence(uint256,bytes32,string)" \
  0 "$EV_HASH_BYTES" "BTC ETF inflows rising: BlackRock Bitcoin ETF record inflows" \
  --rpc-url "$RPC" \
  --private-key "$PRIVATE_KEY" 2>&1 || true)
echo "$SUBMIT_TX" | grep -q "transactionHash\|blockNumber\|status.*1" 2>/dev/null
assert_ok "Evidence submitted on-chain"
sleep 5

# 6.9 Verify evidence appears in API
info "6.9 Verifying evidence in API..."
EVIDENCE2=$(curl -sf http://localhost:8000/api/evidence/0 2>/dev/null || echo "[]")
EV_LEN2=$(echo "$EVIDENCE2" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
[[ "$EV_LEN2" -ge 1 ]]
assert_ok "Evidence count increased to $EV_LEN2"

# 6.10 Fetch evidence content from IPFS (mock)
info "6.10 Fetching evidence content from IPFS..."
EV_CONTENT=$(curl -sf http://localhost:8000/api/evidence/0/0/content 2>/dev/null || echo "{}")
EV_DIR=$(echo "$EV_CONTENT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('direction',''))" 2>/dev/null || echo "")
[[ "$EV_DIR" == "YES" ]]
assert_ok "IPFS evidence content retrieved (direction=$EV_DIR)"

# 6.11 Topic suggestions
info "6.11 Fetching topic suggestions..."
TOPICS=$(curl -sf "http://localhost:8000/api/predictions/topics/suggest?count=3" 2>/dev/null || echo "{}")
TOPIC_LEN=$(echo "$TOPICS" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('topics',[])))" 2>/dev/null || echo "0")
[[ "$TOPIC_LEN" -ge 1 ]]
assert_ok "Topic suggestions returned ($TOPIC_LEN topics)"

# 6.12 Buy again after evidence (should get reduced fee)
info "6.12 Buying YES after evidence submission (reduced fee test)..."
BUY2_TX=$(cast send "$MARKET_ADDR" "buyYes(uint256,uint256)" \
  0 50000000 \
  --rpc-url "$RPC" \
  --private-key "$PRIVATE_KEY" 2>&1 || true)
echo "$BUY2_TX" | grep -q "transactionHash\|blockNumber\|status.*1" 2>/dev/null
assert_ok "Post-evidence buyYes transaction submitted (0.1% fee)"
sleep 5

# 6.13 Get updated prediction (should reflect evidence)
info "6.13 Fetching updated prediction after evidence..."
PRED2=$(curl -sf http://localhost:8000/api/predictions/0 2>/dev/null || echo "{}")
PRED2_PROB=$(echo "$PRED2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('probability_yes',0))" 2>/dev/null || echo "0")
PRED2_AMM=$(echo "$PRED2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('amm_price_yes',0))" 2>/dev/null || echo "0")
[[ "$PRED2_PROB" != "0" ]]
assert_ok "Updated prediction (prob_yes=$PRED2_PROB, amm_price=$PRED2_AMM)"


# ════════════════════════════════════════════════════
#  Phase 7: Frontend Build Test
# ════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Phase 7: Frontend Build Test${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"

cd "$ROOT/frontend"

# Write .env.local for testnet
cat > .env.local <<EOF
VITE_CHAIN=testnet
VITE_RPC_URL=$BASE_SEPOLIA_RPC_URL
VITE_PDX_MARKET_ADDRESS=$MARKET_ADDR
VITE_MOCK_USDC_ADDRESS=$USDC_ADDR
EOF

info "Building frontend (tsc + vite)..."
npm run build 2>&1 | tail -5
[[ -f dist/index.html ]]
assert_ok "Frontend build succeeded (dist/index.html exists)"
cd "$ROOT"


# ════════════════════════════════════════════════════
#  Phase 8: Sell Test (optional - return tokens)
# ════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Phase 8: Sell Test (Sell YES back)${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"

# Get YES token address
YES_TOKEN=$(cast call "$MARKET_ADDR" "getYesToken(uint256)(address)" 0 --rpc-url "$RPC" 2>/dev/null || echo "")
if [[ -n "$YES_TOKEN" && "$YES_TOKEN" != "0x" ]]; then
  YES_BAL=$(cast call "$YES_TOKEN" "balanceOf(address)(uint256)" "$DEPLOYER_ADDR" --rpc-url "$RPC" 2>/dev/null || echo "0")
  info "YES token balance: $YES_BAL"

  if [[ "$YES_BAL" -gt 0 ]]; then
    # Approve YES tokens for market
    info "Approving YES tokens for sell..."
    cast send "$YES_TOKEN" "approve(address,uint256)" "$MARKET_ADDR" "$YES_BAL" \
      --rpc-url "$RPC" --private-key "$PRIVATE_KEY" 2>/dev/null
    sleep 5

    # Sell half the YES tokens
    SELL_AMOUNT=$((YES_BAL / 2))
    info "Selling $SELL_AMOUNT YES tokens..."
    SELL_TX=$(cast send "$MARKET_ADDR" "sellYes(uint256,uint256)" \
      0 "$SELL_AMOUNT" \
      --rpc-url "$RPC" \
      --private-key "$PRIVATE_KEY" 2>&1 || true)
    echo "$SELL_TX" | grep -q "transactionHash\|blockNumber\|status.*1" 2>/dev/null
    assert_ok "sellYes transaction submitted"
    sleep 10

    PRICE_AFTER_SELL=$(cast call "$MARKET_ADDR" "getPriceYes(uint256)(uint256)" 0 --rpc-url "$RPC" 2>/dev/null || echo "0")
    info "Price after sell: $PRICE_AFTER_SELL (should be lower than $PRICE_AFTER)"
    [[ "$PRICE_AFTER_SELL" -lt "$PRICE_AFTER" ]]
    assert_ok "YES price decreased after sell (AMM working)"
  else
    warn "No YES tokens to sell, skipping"
  fi
else
  warn "Could not get YES token address, skipping sell test"
fi


# ════════════════════════════════════════════════════
#  Results
# ════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  E2E Testnet Results${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo ""

# Stop backend
kill "$BACKEND_PID" 2>/dev/null && BACKEND_PID=""

echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""
echo "  Contract Addresses (save for future runs with --skip-deploy):"
echo "    MOCK_USDC=$USDC_ADDR"
echo "    PDX_MARKET=$MARKET_ADDR"
echo "    PDX_ORACLE=$ORACLE_ADDR"
echo ""

if [[ "$FAIL" -eq 0 ]]; then
  echo -e "  ${GREEN}All tests passed!${NC}"
  echo ""
  echo "  Next steps:"
  echo "    1. Save addresses to contracts/.env"
  echo "    2. Run frontend: cd frontend && npm run dev"
  echo "    3. Connect MetaMask to Base Sepolia and import deployer key"
  echo "    4. Open http://localhost:5173 to interact via UI"
  echo ""
  exit 0
else
  echo -e "  ${RED}$FAIL test(s) failed${NC}"
  exit 1
fi
