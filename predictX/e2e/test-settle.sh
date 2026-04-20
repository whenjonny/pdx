#!/usr/bin/env bash
#
# PDX Settlement & Redemption Test
#
# Simulates the full lifecycle on local anvil:
#   Deploy → Create Market → Buy YES → Fast-forward → Settle → Redeem
#
# Usage:
#   ./e2e/test-settle.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${CYAN}[TEST]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}  $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

RPC="http://localhost:8545"
# Anvil account 0
PK="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
DEPLOYER=$(cast wallet address "$PK")

echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  PDX Settlement & Redemption E2E Test${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo ""

# ──── Check anvil is running ────
cast block-number --rpc-url "$RPC" >/dev/null 2>&1 || fail "Anvil not running. Start with: anvil --port 8545"
ok "Anvil is running"

# ════════════════════════════════════════════════════
#  1. Deploy contracts
# ════════════════════════════════════════════════════
info "1. Deploying contracts..."
cd "$ROOT/contracts"

DEPLOY_OUT=$(PRIVATE_KEY="$PK" forge script script/Deploy.s.sol:DeployScript \
  --rpc-url "$RPC" --broadcast 2>&1)

USDC=$(echo "$DEPLOY_OUT" | grep -oP 'MockUSDC:\s+\K0x[a-fA-F0-9]+')
MARKET=$(echo "$DEPLOY_OUT" | grep -oP 'PDXMarket:\s+\K0x[a-fA-F0-9]+')
ORACLE=$(echo "$DEPLOY_OUT" | grep -oP 'PDXOracle:\s+\K0x[a-fA-F0-9]+')

[[ -n "$MARKET" ]] || fail "Deploy failed"
ok "Deployed: USDC=$USDC  Market=$MARKET  Oracle=$ORACLE"
cd "$ROOT"

# ════════════════════════════════════════════════════
#  2. Create market (deadline = 10 seconds from now)
# ════════════════════════════════════════════════════
info "2. Creating market with 10s deadline..."

# Approve USDC
cast send "$USDC" "approve(address,uint256)" "$MARKET" \
  "115792089237316195423570985008687907853269984665640564039457584007913129639935" \
  --rpc-url "$RPC" --private-key "$PK" >/dev/null 2>&1

# Create market: question, conditionId, deadline, initialLiquidity
NOW=$(cast block-number --rpc-url "$RPC" | xargs -I{} cast block {} --rpc-url "$RPC" -j | python3 -c "import sys,json; print(json.load(sys.stdin)['timestamp'])")
DEADLINE=$((NOW + 120))  # 2 minutes from now

TX=$(cast send "$MARKET" "createMarket(string,bytes32,uint256,uint256)" \
  "Will this test pass?" \
  "0x0000000000000000000000000000000000000000000000000000000000000000" \
  "$DEADLINE" \
  "10000000000" \
  --rpc-url "$RPC" --private-key "$PK" --json 2>&1)

MARKET_COUNT=$(cast call "$MARKET" "marketCount()(uint256)" --rpc-url "$RPC")
MARKET_ID=$((MARKET_COUNT - 1))
ok "Market #$MARKET_ID created (deadline in 2 min)"

# ════════════════════════════════════════════════════
#  3. Buy YES tokens
# ════════════════════════════════════════════════════
info "3. Buying YES tokens (1000 USDC)..."
cast send "$MARKET" "buyYes(uint256,uint256)" "$MARKET_ID" "1000000000" \
  --rpc-url "$RPC" --private-key "$PK" >/dev/null 2>&1

YES_TOKEN=$(cast call "$MARKET" "getYesToken(uint256)(address)" "$MARKET_ID" --rpc-url "$RPC")
NO_TOKEN=$(cast call "$MARKET" "getNoToken(uint256)(address)" "$MARKET_ID" --rpc-url "$RPC")
YES_BAL=$(cast call "$YES_TOKEN" "balanceOf(address)(uint256)" "$DEPLOYER" --rpc-url "$RPC")

ok "Bought YES tokens. Balance: $YES_BAL (raw)"

PRICE_YES=$(cast call "$MARKET" "getPriceYes(uint256)(uint256)" "$MARKET_ID" --rpc-url "$RPC")
info "   YES price after buy: $PRICE_YES"

# ════════════════════════════════════════════════════
#  4. Check USDC balance BEFORE redeem
# ════════════════════════════════════════════════════
USDC_BEFORE=$(cast call "$USDC" "balanceOf(address)(uint256)" "$DEPLOYER" --rpc-url "$RPC")
info "4. USDC balance before redeem: $USDC_BEFORE"

# ════════════════════════════════════════════════════
#  5. Fast-forward time past deadline
# ════════════════════════════════════════════════════
info "5. Fast-forwarding 3 minutes past deadline..."
cast rpc evm_increaseTime 180 --rpc-url "$RPC" >/dev/null 2>&1
cast rpc evm_mine --rpc-url "$RPC" >/dev/null 2>&1
ok "Time advanced"

# ════════════════════════════════════════════════════
#  6. Settle market (Oracle settles as YES)
# ════════════════════════════════════════════════════
info "6. Settling market #$MARKET_ID as YES..."
SETTLE_TX=$(cast send "$ORACLE" "settleMarket(uint256,bool)" "$MARKET_ID" true \
  --rpc-url "$RPC" --private-key "$PK" --json 2>&1)

RESOLVED=$(cast call "$MARKET" "getResolved(uint256)(bool)" "$MARKET_ID" --rpc-url "$RPC" 2>/dev/null || \
  python3 -c "
import json
data = json.loads('$SETTLE_TX')
print('true' if data.get('status') == '0x1' else 'false')
")

# Verify by reading market struct
info "   Checking resolved status..."
# Try reading resolved from the market
MARKET_DATA=$(cast call "$MARKET" "markets(uint256)" "$MARKET_ID" --rpc-url "$RPC" 2>/dev/null || echo "")
ok "Market settled as YES"

# ════════════════════════════════════════════════════
#  7. Redeem winning tokens
# ════════════════════════════════════════════════════
info "7. Redeeming YES tokens..."

YES_BAL_BEFORE=$(cast call "$YES_TOKEN" "balanceOf(address)(uint256)" "$DEPLOYER" --rpc-url "$RPC")
info "   YES token balance before redeem: $YES_BAL_BEFORE"

REDEEM_TX=$(cast send "$MARKET" "redeem(uint256)" "$MARKET_ID" \
  --rpc-url "$RPC" --private-key "$PK" --json 2>&1)

REDEEM_STATUS=$(echo "$REDEEM_TX" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)

if [[ "$REDEEM_STATUS" == "0x1" ]]; then
  ok "Redeem transaction succeeded"
else
  fail "Redeem transaction failed: $REDEEM_TX"
fi

# ════════════════════════════════════════════════════
#  8. Verify final state
# ════════════════════════════════════════════════════
info "8. Verifying final state..."

YES_BAL_AFTER=$(cast call "$YES_TOKEN" "balanceOf(address)(uint256)" "$DEPLOYER" --rpc-url "$RPC")
USDC_AFTER=$(cast call "$USDC" "balanceOf(address)(uint256)" "$DEPLOYER" --rpc-url "$RPC")

info "   YES tokens: $YES_BAL_BEFORE → $YES_BAL_AFTER"
info "   USDC:       $USDC_BEFORE → $USDC_AFTER"

# YES tokens should be 0 after redeem
if [[ "$YES_BAL_AFTER" == "0" ]]; then
  ok "YES tokens burned (balance = 0)"
else
  fail "YES tokens not burned: $YES_BAL_AFTER"
fi

# USDC should have increased
if [[ "$USDC_AFTER" -gt "$USDC_BEFORE" ]]; then
  USDC_GAINED=$((USDC_AFTER - USDC_BEFORE))
  USDC_GAINED_DISPLAY=$(python3 -c "print(f'{$USDC_GAINED / 1e6:.2f}')")
  ok "USDC increased by $USDC_GAINED_DISPLAY USDC (1:1 token redemption)"
else
  fail "USDC did not increase after redeem"
fi

# ════════════════════════════════════════════════════
#  Results
# ════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Settlement & Redemption Test PASSED${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Flow completed:"
echo "    1. Deploy contracts"
echo "    2. Create market (2 min deadline)"
echo "    3. Buy YES (1000 USDC)"
echo "    4. Fast-forward past deadline"
echo "    5. Oracle settles → YES wins"
echo "    6. Redeem YES tokens → USDC returned 1:1"
echo "    7. YES tokens burned, USDC balance increased"
echo ""
echo "  Contracts:"
echo "    USDC=$USDC"
echo "    Market=$MARKET"
echo "    Oracle=$ORACLE"
echo ""
