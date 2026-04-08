# PDX 测试流程

本文档覆盖本地 E2E 测试和 Base Sepolia 测试网测试的完整流程。

---

## 一、本地 E2E 测试 (Anvil)

无需 MetaMask 或浏览器，全部通过命令行完成。

### 前置条件

| 工具 | 安装方式 |
|------|----------|
| Foundry (anvil, forge, cast) | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| Python >= 3.10 | https://python.org |
| Node.js >= 18 | https://nodejs.org |
| jq (可选) | `brew install jq` |

### Step 0: 启动环境

打开 **3 个终端**：

**终端 1 — Anvil 本地链：**

```bash
anvil --port 8545 --chain-id 31337 --block-time 1
```

**终端 2 — 部署合约：**

```bash
cd contracts
forge script script/Deploy.s.sol:DeployScript \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --broadcast
```

记下 3 个地址并设置环境变量：

```bash
export USDC=0x5FbDB2315678afecb367f032d93F642f64180aa3
export MARKET=0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
export ORACLE=0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0
```

**终端 3 — 启动后端：**

```bash
cd backend && source .venv/bin/activate
export RPC_URL=http://localhost:8545 CHAIN_ID=31337
export PDX_MARKET_ADDRESS=$MARKET MOCK_USDC_ADDRESS=$USDC PDX_ORACLE_ADDRESS=$ORACLE
export USE_MOCK_MIROFISH=true
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 1: 健康检查

```bash
curl -s http://localhost:8000/api/health | jq
# 期望: {"status":"ok","chain_connected":true}
```

### Step 2: 创建市场

```bash
curl -s -X POST http://localhost:8000/api/markets \
  -H "Content-Type: application/json" \
  -d '{"question":"Will BTC exceed $100K by June 2026?","initial_liquidity":10000,"deadline_days":30}' | jq
# 期望: market_id=0, initial_liquidity=10000000000
```

### Step 3: 查看市场

```bash
curl -s http://localhost:8000/api/markets | jq
# 验证: priceYes ≈ 0.5, priceNo ≈ 0.5, resolved=false
```

### Step 4: 查看 AI 预测

```bash
curl -s http://localhost:8000/api/predictions/0 | jq
# 期望: probability_yes ≈ 0.5, source="MiroFish Mock"
```

### Step 5: 链上交易

```bash
# Anvil 测试账户
TRADER_A_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
TRADER_A=0x70997970C51812dc3A010C7d01b50e0d17dc79C8

# Mint USDC
cast send $USDC "mint(address,uint256)" $TRADER_A 50000000000 \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

# Approve
cast send $USDC "approve(address,uint256)" $MARKET $(cast max-uint) \
  --rpc-url http://localhost:8545 --private-key $TRADER_A_KEY

# Buy YES: 1000 USDC
cast send $MARKET "buyYes(uint256,uint256)" 0 1000000000 \
  --rpc-url http://localhost:8545 --private-key $TRADER_A_KEY

# 验证价格变动
cast call $MARKET "getPriceYes(uint256)(uint256)" 0 --rpc-url http://localhost:8545
# 期望: > 500000 (即 > $0.50)
```

### Step 6: 提交证据

```bash
# 上传到 IPFS (mock)
curl -s -X POST http://localhost:8000/api/evidence/upload \
  -H "Content-Type: application/json" \
  -d '{"market_id":0,"title":"BTC Analysis","content":"Based on halving cycles, BTC likely exceeds 100K.","source_url":"https://example.com","direction":"YES"}' | jq

# 链上提交 (使用返回的 ipfs_hash)
cast send $MARKET "submitEvidence(uint256,bytes32,string)" \
  0 0x<hash> "BTC halving cycle analysis" \
  --rpc-url http://localhost:8545 --private-key $TRADER_A_KEY

# 验证
curl -s http://localhost:8000/api/evidence/0 | jq
```

### Step 7: 前端构建验证

```bash
cd frontend
echo "VITE_CHAIN=local
VITE_PDX_MARKET_ADDRESS=$MARKET
VITE_MOCK_USDC_ADDRESS=$USDC" > .env.local
npm run build
# 期望: dist/index.html 生成成功
```

---

## 二、结算测试 (Anvil)

使用自动化脚本测试完整结算流程：

```bash
cd e2e
bash test-settle.sh
```

8 个步骤自动执行：
1. 部署合约
2. 创建市场（2 分钟 deadline）
3. 买入 YES tokens
4. Fast-forward 时间到 deadline 后
5. Oracle 结算（YES wins）
6. Redeem 兑换 USDC
7. 验证 token 被 burn
8. 验证 USDC 余额增加

---

## 三、测试网 E2E 测试 (Base Sepolia)

### 自动化测试

```bash
cd e2e
bash testnet-deploy.sh          # 完整流程
bash testnet-deploy.sh --skip-deploy  # 跳过部署（已有合约地址）
```

### 8 个测试阶段

```
Phase 1: Prerequisites Check
  ├── 检查工具链 (forge, cast, python3, node)
  ├── 加载 contracts/.env
  └── 验证 deployer 有 ETH

Phase 2: Contract Deployment
  ├── forge test（先跑单元测试）
  ├── forge script Deploy.s.sol → Base Sepolia
  └── 提取合约地址

Phase 3: On-chain Verification
  ├── MockUSDC / PDXMarket / Oracle 合约响应检查
  └── deployer USDC 余额

Phase 4: Create Sample Market
  ├── 创建示例市场
  └── 验证 YES price > 0

Phase 5: Trading Test (Buy YES)
  ├── Approve USDC → PDXMarket
  ├── buyYes(0, 100 USDC)
  └── 验证价格上涨（AMM 生效）

Phase 6: Backend API Test
  ├── GET /api/health, /api/markets
  ├── POST /api/evidence/upload → cast submitEvidence
  ├── GET /api/predictions/0 (MiroFish)
  └── buyYes after evidence (0.1% fee)

Phase 7: Frontend Build Test
  ├── 配置 .env.local (testnet mode)
  └── npm run build

Phase 8: Sell Test
  ├── sellYes (卖回一半)
  └── 验证价格下降
```

### 端到端验证 (Agent 流程)

```
1. Agent: /pdx-markets          → 显示市场列表
2. Agent: /pdx-analyze 1        → Web 搜索 + embedding + Monte Carlo
3. Agent: /pdx-submit 1 --direction YES  → IPFS + 签名链接
4. 用户点击链接                   → MetaMask 签名 → Evidence 上链
5. Agent: /pdx-trade 1 --amount 100      → 交易签名链接
6. 用户点击链接                   → MetaMask 确认 → 获得 YES tokens
```

### 期望输出

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

## 四、数据流

```
用户提交证据
    ├─→ POST /api/evidence/upload → IPFS pin → CID + bytes32 hash
    ├─→ cast submitEvidence(marketId, bytes32, summary) → 链上存储
    └─→ hasEvidence[user]=true → 下次交易手续费 0.1%

MiroFish 定时分析 (每5分钟)
    ├─→ blockchain_service.list_markets() → 活跃市场
    ├─→ blockchain_service.get_evidence_list() → 链上证据列表
    ├─→ ipfs_service.fetch_by_hash() → IPFS 全文内容
    └─→ analyze_market() → LLM/启发式 → 概率

前端展示
    ├─→ AMM 价格 → "Market Price" (真实成交价)
    └─→ MiroFish → "AI Reference" (参考值)
```

---

## 五、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `insufficient funds` | 测试 ETH 不够 | 去水龙头领取（见 [安装指引](./installation.md)） |
| `could not connect` | RPC URL 错误 | 检查 Alchemy/Anvil 是否运行 |
| `nonce too low` | 之前的交易未确认 | 等几秒重试 |
| Backend 504 | RPC 限流 | 换 RPC provider 或稍等 |
| Price 没变化 | 交易可能没上链 | 检查 BaseScan tx hash |
| IPFS content 404 | CID 在内存中，重启丢失 | 重新上传或配置 Pinata |
| `chain_connected: false` | anvil 未运行 | 启动 anvil |
| 前端白屏 | 合约地址未配置 | 检查 `.env.local` |
| MetaMask 不弹出 | 网络未切换 | MetaMask 切到 Base Sepolia |
| `sentence-transformers` 安装慢 | 模型较大 | `pip install --no-deps` 后手动装依赖 |

---

## 六、手动浏览器验证

部署完成后可在浏览器上验证：

1. 打开 https://sepolia.basescan.org
2. 搜索 PDXMarket 地址
3. Contract → Read Contract → `getPriceYes(0)` 查看价格
4. Contract → Write Contract → 连接 MetaMask 进行交易
