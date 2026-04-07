# PDX 端到端测试指南

本文档提供完整的端到端 (E2E) 测试流程，覆盖从启动环境到完成市场全生命周期的每一步。所有操作均可通过命令行完成，无需 MetaMask 或浏览器。

---

## 前置条件

| 工具 | 安装方式 |
|------|----------|
| Foundry (anvil, forge, cast) | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| Python >= 3.10 | `brew install python` 或 https://python.org |
| Node.js >= 18 | `brew install node` 或 https://nodejs.org |
| curl | macOS 自带 |
| jq (可选，美化 JSON) | `brew install jq` |

---

## Step 0: 启动本地环境

打开 **3 个终端窗口**。

### 终端 1 — 启动 Anvil 本地链

```bash
anvil --port 8545 --chain-id 31337 --block-time 1
```

保持运行。Anvil 会预置 10 个测试账户，每个有 10,000 ETH。

### 终端 2 — 部署合约

```bash
cd /Users/user/Desktop/vault/03-Projects/NUS/FT5004/pdx/contracts

forge script script/Deploy.s.sol:DeployScript \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --broadcast
```

**记下输出的 3 个地址**，后续步骤需要用到。示例：

```
MockUSDC:   0x5FbDB2315678afecb367f032d93F642f64180aa3
PDXMarket:  0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
PDXOracle:  0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0
```

> 以下命令中用 `$USDC`、`$MARKET`、`$ORACLE` 表示这三个地址。
> 你可以直接设置环境变量：
> ```bash
> export USDC=0x5FbDB2315678afecb367f032d93F642f64180aa3
> export MARKET=0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
> export ORACLE=0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0
> ```

### 终端 3 — 启动后端

```bash
cd /Users/user/Desktop/vault/03-Projects/NUS/FT5004/pdx/backend
source .venv/bin/activate

export RPC_URL=http://localhost:8545
export CHAIN_ID=31337
export PDX_MARKET_ADDRESS=$MARKET
export MOCK_USDC_ADDRESS=$USDC
export PDX_ORACLE_ADDRESS=$ORACLE
export USE_MOCK_MIROFISH=true

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Step 1: 健康检查

验证后端连接到区块链：

```bash
curl -s http://localhost:8000/api/health | jq
```

**期望输出：**
```json
{
  "status": "ok",
  "chain_connected": true,
  "market_address": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
}
```

**检查点：** `chain_connected` 必须为 `true`。如果为 `false`，检查 anvil 是否在运行。

---

## Step 2: 创建预测市场

```bash
curl -s -X POST http://localhost:8000/api/markets \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Will BTC exceed $100K by June 2026?",
    "initial_liquidity": 10000,
    "deadline_days": 30
  }' | jq
```

**期望输出：**
```json
{
  "market_id": 0,
  "question": "Will BTC exceed $100K by June 2026?",
  "deadline": 1749196800,
  "initial_liquidity": "10000000000",
  "tx_hash": "0x..."
}
```

**检查点：** `market_id` 为 0（第一个市场），`initial_liquidity` 为 `10000000000`（10,000 USDC，6 位小数）。

可以创建多个市场：

```bash
curl -s -X POST http://localhost:8000/api/markets \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Will ETH transition to full L2-centric roadmap by 2027?",
    "initial_liquidity": 5000,
    "deadline_days": 60
  }' | jq
```

---

## Step 3: 查看市场列表

```bash
curl -s http://localhost:8000/api/markets | jq
```

**期望输出：** 返回数组，包含刚创建的市场。

**关键字段验证：**
- `priceYes` ≈ 0.5（初始 50/50）
- `priceNo` ≈ 0.5
- `resolved` = false
- `totalDeposited` = 初始流动性值

查看单个市场详情：

```bash
curl -s http://localhost:8000/api/markets/0 | jq
```

---

## Step 4: 查看 AI 预测

```bash
curl -s http://localhost:8000/api/predictions/0 | jq
```

**期望输出：**
```json
{
  "market_id": 0,
  "probability_yes": 0.5234,
  "probability_no": 0.4766,
  "confidence": 0.35,
  "reasoning": "Insufficient evidence to form a strong opinion. Market is roughly balanced.",
  "source": "MiroFish Mock",
  "amm_price_yes": 0.5,
  "updated_at": 0
}
```

**检查点：**
- 使用 Mock 模式时，`probability_yes` 应在当前 AMM 价格附近（±0.05 随机噪声），`probability_yes + probability_no = 1`
- `confidence` 为 0~1 的数值（非字符串）
- `updated_at` 为 Unix 时间戳（整数），例如 `1744000000`

---

## Step 5: 使用 cast 进行链上交易

> **前提：** 执行本节所有命令前，必须先在当前终端设置合约地址环境变量（Step 0 部署完成后记下的地址）：
> ```bash
> export USDC=0x5FbDB2315678afecb367f032d93F642f64180aa3
> export MARKET=0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
> export ORACLE=0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0
> ```
> 若未设置，`cast call $USDC ...` 会因变量为空而报 `odd number of digits` 错误。

以下使用 Anvil 测试账户进行交易。Anvil 预置了 10 个账户：

| 账户 | 地址 | 私钥 |
|------|------|------|
| Account 0 (部署者) | 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 | 0xac0974...ff80 |
| Account 1 (交易者 A) | 0x70997970C51812dc3A010C7d01b50e0d17dc79C8 | 0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d |
| Account 2 (交易者 B) | 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC | 0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a |

### 5a. 给交易者 Mint USDC

```bash
# 通过 API mint
curl -s -X POST http://localhost:8000/api/markets/mint-usdc \
  -H "Content-Type: application/json" \
  -d '{"to": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8", "amount": 50000}' | jq

# 或直接用 cast
cast send $USDC "mint(address,uint256)" \
  0x70997970C51812dc3A010C7d01b50e0d17dc79C8 50000000000 \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```

**验证余额：**
```bash
cast call $USDC "balanceOf(address)(uint256)" \
  0x70997970C51812dc3A010C7d01b50e0d17dc79C8 \
  --rpc-url http://localhost:8545
```

**期望：** `50000000000`（50,000 USDC）

### 5b. Approve 并买入 YES

```bash
TRADER_A_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d

# Approve
cast send $USDC "approve(address,uint256)" $MARKET \
  $(cast max-uint) \
  --rpc-url http://localhost:8545 \
  --private-key $TRADER_A_KEY

# Buy YES: 1000 USDC
cast send $MARKET "buyYes(uint256,uint256)" 0 1000000000 \
  --rpc-url http://localhost:8545 \
  --private-key $TRADER_A_KEY
```

**验证价格变动：**
```bash
# YES 价格应该升高（> 0.5）
cast call $MARKET "getPriceYes(uint256)(uint256)" 0 --rpc-url http://localhost:8545

# NO 价格应该降低（< 0.5）
cast call $MARKET "getPriceNo(uint256)(uint256)" 0 --rpc-url http://localhost:8545
```

**检查点：** `getPriceYes` 返回值 > 500000（即 > $0.50），`getPriceNo` < 500000。

也可以用 API 验证：
```bash
curl -s http://localhost:8000/api/markets/0 | jq '{priceYes, priceNo, totalDeposited}'
```

### 5c. 另一个交易者买入 NO

```bash
TRADER_B_KEY=0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a
TRADER_B_ADDR=0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC

# Mint USDC
curl -s -X POST http://localhost:8000/api/markets/mint-usdc \
  -H "Content-Type: application/json" \
  -d "{\"to\": \"$TRADER_B_ADDR\", \"amount\": 50000}" | jq

# Approve
cast send $USDC "approve(address,uint256)" $MARKET \
  $(cast max-uint) \
  --rpc-url http://localhost:8545 \
  --private-key $TRADER_B_KEY

# Buy NO: 2000 USDC
cast send $MARKET "buyNo(uint256,uint256)" 0 2000000000 \
  --rpc-url http://localhost:8545 \
  --private-key $TRADER_B_KEY
```

**验证：** YES 价格应回落（NO 买盘推低 YES 价格）。

---

## Step 6: 提交证据

### 6a. 上传证据到 IPFS（Mock）

```bash
curl -s -X POST http://localhost:8000/api/evidence/upload \
  -H "Content-Type: application/json" \
  -d '{
    "market_id": 0,
    "title": "BTC Technical Analysis",
    "content": "Based on historical halving cycles and current ETF inflows, BTC is likely to exceed 100K.",
    "source_url": "https://example.com/btc-analysis",
    "direction": "YES"
  }' | jq
```

**期望输出：**
```json
{
  "cid": "Qm...",
  "evidenceHash": "0x..."
}
```

### 6b. 将证据提交到链上

用返回的 `evidenceHash` 调用合约：

```bash
EVIDENCE_HASH="<上一步返回的 evidenceHash>"

cast send $MARKET "submitEvidence(uint256,bytes32,string)" \
  0 \
  $EVIDENCE_HASH \
  "BTC halving cycle analysis supports YES outcome" \
  --rpc-url http://localhost:8545 \
  --private-key $TRADER_A_KEY
```

### 6c. 验证证据

```bash
# 链上查询
cast call $MARKET "getEvidenceCount(uint256)(uint256)" 0 --rpc-url http://localhost:8545
# 期望: 1

# 通过 API
curl -s http://localhost:8000/api/evidence/0 | jq
```

### 6d. 验证手续费折扣

提交证据后，该用户的交易手续费从 0.3% 降为 0.1%：

```bash
# 检查 hasEvidence
cast call $MARKET "hasEvidence(address,uint256)(bool)" \
  0x70997970C51812dc3A010C7d01b50e0d17dc79C8 0 \
  --rpc-url http://localhost:8545
# 期望: true
```

再次买入，手续费将为 0.1%：

```bash
cast send $MARKET "buyYes(uint256,uint256)" 0 500000000 \
  --rpc-url http://localhost:8545 \
  --private-key $TRADER_A_KEY
```

---

## Step 7: 查看交易后的 AI 预测

```bash
curl -s http://localhost:8000/api/predictions/0 | jq
```

**检查点：** `probability` 应反映当前 AMM 价格（买入 YES 多则概率偏高）。

---

## Step 8: 结算市场

> 注意：正式市场必须过了 deadline 才能结算。本地测试可以用 `cast` 快进时间。

### 8a. 快进时间（跳过等待期）

```bash
# 快进 31 天
cast rpc evm_increaseTime 2678400 --rpc-url http://localhost:8545
cast rpc evm_mine --rpc-url http://localhost:8545
```

### 8b. 结算市场

```bash
# YES 获胜
curl -s -X POST http://localhost:8000/api/markets/settle \
  -H "Content-Type: application/json" \
  -d '{"market_id": 0, "outcome": true}' | jq
```

**期望输出：**
```json
{
  "market_id": 0,
  "outcome": true,
  "tx_hash": "0x..."
}
```

**验证：**
```bash
curl -s http://localhost:8000/api/markets/0 | jq '{resolved, outcome}'
# 期望: {"resolved": true, "outcome": true}
```

---

## Step 9: 赎回收益

YES token 持有者（交易者 A）可以 1:1 兑换 USDC：

```bash
# 查看交易者 A 的 YES token 余额
# 先获取 YES token 地址
YES_TOKEN=$(cast call $MARKET "getMarketTokens(uint256)(address,address)" 0 --rpc-url http://localhost:8545 | head -1)

cast call $YES_TOKEN "balanceOf(address)(uint256)" \
  0x70997970C51812dc3A010C7d01b50e0d17dc79C8 \
  --rpc-url http://localhost:8545
```

**赎回：**
```bash
cast send $MARKET "redeem(uint256)" 0 \
  --rpc-url http://localhost:8545 \
  --private-key $TRADER_A_KEY
```

**验证 USDC 余额增加：**
```bash
cast call $USDC "balanceOf(address)(uint256)" \
  0x70997970C51812dc3A010C7d01b50e0d17dc79C8 \
  --rpc-url http://localhost:8545
```

**检查点：** 赎回后，YES token 余额归零，USDC 余额增加对应数量。

---

## Step 10: Agent SDK 端到端

在第 4 个终端中：

```bash
cd /Users/user/Desktop/vault/03-Projects/NUS/FT5004/pdx/sdk
pip install -e .
```

### 运行简单交易示例

```bash
RPC_URL=http://localhost:8545 \
PRIVATE_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d \
PDX_MARKET=$MARKET \
MOCK_USDC=$USDC \
BACKEND_URL=http://localhost:8000 \
python3 examples/simple_trade.py
```

### 运行完整 Agent 流程

```bash
RPC_URL=http://localhost:8545 \
PRIVATE_KEY=0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a \
PDX_MARKET=$MARKET \
MOCK_USDC=$USDC \
BACKEND_URL=http://localhost:8000 \
python3 examples/agent_trade.py
```

**期望：** 脚本完成 mint → approve → evidence → trade → 打印持仓。

---

## Step 11: 前端 UI 验证（可选）

启动前端：

```bash
cd /Users/user/Desktop/vault/03-Projects/NUS/FT5004/pdx/frontend

cat > .env.local <<EOF
VITE_CHAIN=local
VITE_PDX_MARKET_ADDRESS=$MARKET
VITE_MOCK_USDC_ADDRESS=$USDC
EOF

npm run dev
```

打开 http://localhost:5173，验证：

| 页面 | 验证内容 |
|------|----------|
| 首页 | 显示已创建的市场列表，价格条显示 YES/NO 百分比 |
| 市场详情 | 价格、倒计时、交易面板、证据列表、AI 预测概率 |
| Faucet | 连接钱包后可 mint 10,000 USDC |
| 交易 | 连接 MetaMask → Buy YES/NO → 持仓显示 |
| 已结算市场 | 显示 "Settled: YES/NO" 标签，赢家看到 "Claim USDC" 按钮 |

> MetaMask 添加 Anvil 本地网络：RPC `http://localhost:8545`，Chain ID `31337`。
> 导入测试账户：使用上面表格中的私钥。

---

## 完整测试检查清单

```
环境
  [ ] anvil 启动，端口 8545
  [ ] 合约部署成功，3 个地址记录
  [ ] 后端启动，/api/health 返回 chain_connected: true

市场生命周期
  [ ] POST /api/markets 创建市场成功
  [ ] GET /api/markets 返回市场列表
  [ ] GET /api/markets/0 返回市场详情，priceYes ≈ 0.5

交易
  [ ] mint USDC 给交易者
  [ ] approve + buyYes 成功，YES 价格上升
  [ ] approve + buyNo 成功，YES 价格回落
  [ ] 交易后 totalDeposited 增加

证据
  [ ] POST /api/evidence/upload 返回 CID + hash
  [ ] submitEvidence 链上提交成功
  [ ] getEvidenceCount 返回 1
  [ ] hasEvidence 返回 true
  [ ] 后续交易手续费为 0.1%（而非 0.3%）

AI 预测
  [ ] GET /api/predictions/0 返回概率 + 置信度 + 推理

结算 & 赎回
  [ ] evm_increaseTime 快进 31 天
  [ ] POST /api/markets/settle 结算成功
  [ ] resolved = true, outcome = true/false
  [ ] redeem 赎回成功，USDC 余额增加，YES/NO token 归零

Agent SDK
  [ ] pip install -e ./sdk 成功
  [ ] simple_trade.py 完成交易
  [ ] agent_trade.py 完成完整流程

前端 (可选)
  [ ] 市场列表展示正确
  [ ] 交易面板可买入
  [ ] 证据面板可提交
  [ ] AI 预测显示概率
  [ ] 已结算市场可赎回
```

---

## Step 12: 新增功能 — 市场筛选/排序/搜索

### 12a. 创建多分类市场

```bash
# Crypto 分类
curl -s -X POST http://localhost:8000/api/markets \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Will ETH reach $10K in 2026?",
    "initial_liquidity": 5000,
    "deadline_days": 60,
    "category": "crypto",
    "resolution_source": "https://polymarket.com/event/eth-10k"
  }' | jq

# Politics 分类
curl -s -X POST http://localhost:8000/api/markets \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Will the US pass a federal crypto bill in 2026?",
    "initial_liquidity": 8000,
    "deadline_days": 90,
    "category": "politics",
    "resolution_source": ""
  }' | jq

# Sports 分类
curl -s -X POST http://localhost:8000/api/markets \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Will a European team win the 2026 FIFA World Cup?",
    "initial_liquidity": 3000,
    "deadline_days": 120,
    "category": "sports",
    "resolution_source": ""
  }' | jq
```

### 12b. 按分类筛选

```bash
# 只看 Crypto 分类
curl -s "http://localhost:8000/api/markets?category=crypto" | jq '.[].question'

# 只看 Politics 分类
curl -s "http://localhost:8000/api/markets?category=politics" | jq '.[].question'
```

**检查点：** 各分类只返回对应分类的市场。

### 12c. 排序测试

```bash
# 按成交量排序（高到低）
curl -s "http://localhost:8000/api/markets?sort=volume" | jq '[.[] | {question, totalDeposited}]'

# 按最新创建排序
curl -s "http://localhost:8000/api/markets?sort=newest" | jq '[.[] | {id, question}]'

# 按即将截止排序
curl -s "http://localhost:8000/api/markets?sort=ending_soon" | jq '[.[] | {question, deadline}]'
```

### 12d. 搜索测试

```bash
# 搜索包含 "BTC" 的市场
curl -s "http://localhost:8000/api/markets?search=BTC" | jq '.[].question'
# 期望：只返回包含 BTC 的市场

# 搜索不存在的关键词
curl -s "http://localhost:8000/api/markets?search=ZZZZZ" | jq
# 期望：返回空数组 []
```

### 12e. 状态筛选

```bash
# 只看活跃市场
curl -s "http://localhost:8000/api/markets?status=active" | jq '[.[] | {question, resolved}]'

# 只看已结算市场（Step 8 结算后才有）
curl -s "http://localhost:8000/api/markets?status=resolved" | jq '[.[] | {question, resolved, outcome}]'
```

### 12f. 分页测试

```bash
# 第 1 页，每页 2 个
curl -s "http://localhost:8000/api/markets?page=1&limit=2" | jq 'length'
# 期望：2

# 第 2 页
curl -s "http://localhost:8000/api/markets?page=2&limit=2" | jq 'length'
# 期望：≤2，取决于总市场数
```

### 12g. 组合筛选

```bash
# Crypto 分类 + 按成交量排序 + 只看活跃
curl -s "http://localhost:8000/api/markets?category=crypto&sort=volume&status=active" | jq
```

---

## Step 13: 新增功能 — 平台统计

```bash
curl -s http://localhost:8000/api/stats | jq
```

**期望输出：**
```json
{
  "total_markets": 4,
  "active_markets": 3,
  "total_volume": "26000000000",
  "total_evidence": 1
}
```

**检查点：**
- `total_markets` = 创建的市场总数
- `active_markets` = 未结算且未过期的市场数
- `total_volume` = 所有市场 `totalDeposited` 之和
- `total_evidence` = 所有市场的证据总数

---

## Step 14: 新增功能 — 市场交易记录

```bash
# 获取市场 0 的交易历史
curl -s http://localhost:8000/api/markets/0/trades | jq
```

**期望输出：**
```json
[
  {
    "type": "buy_yes",
    "trader": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "usdc_amount": "500000000",
    "token_amount": "...",
    "fee": "500000",
    "timestamp": 1712345678,
    "tx_hash": "0x...",
    "block_number": 15
  },
  {
    "type": "buy_no",
    "trader": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
    "usdc_amount": "2000000000",
    "token_amount": "...",
    "fee": "6000000",
    "timestamp": 1712345600,
    "tx_hash": "0x...",
    "block_number": 12
  }
]
```

**检查点：**
- 返回按时间倒序排列
- `type` 正确标记为 `buy_yes`/`buy_no`/`sell_yes`/`sell_no`
- `fee` 字段：有证据的交易应该更低（0.1% vs 0.3%）
- 每条记录都有 `tx_hash` 可追溯

---

## Step 15: 新增功能 — 用户个人数据

### 15a. 用户持仓查询

```bash
TRADER_A=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
curl -s "http://localhost:8000/api/users/$TRADER_A/positions" | jq
```

**期望输出：**
```json
[
  {
    "market_id": 0,
    "question": "Will BTC exceed $100K by June 2026?",
    "yes_balance": "1495000000",
    "no_balance": "0",
    "current_price_yes": 0.52,
    "current_price_no": 0.48,
    "market_resolved": false,
    "market_outcome": false,
    "current_value_usdc": "777400000"
  }
]
```

**检查点：**
- 只返回持有 token 的市场（余额 > 0）
- `current_value_usdc` ≈ `yes_balance * current_price_yes + no_balance * current_price_no`
- 无 token 持仓的用户返回空数组 `[]`

### 15b. 用户交易历史

```bash
curl -s "http://localhost:8000/api/users/$TRADER_A/transactions" | jq
```

**期望输出：**
```json
[
  {
    "type": "buy_yes",
    "market_id": 0,
    "timestamp": 1712345678,
    "block_number": 15,
    "tx_hash": "0x...",
    "details": {
      "usdc_in": "500000000",
      "tokens_out": "498000000",
      "fee": "500000",
      "is_yes": true
    }
  },
  {
    "type": "submit_evidence",
    "market_id": 0,
    "timestamp": 1712345600,
    "block_number": 14,
    "tx_hash": "0x...",
    "details": {
      "ipfs_hash": "0x...",
      "summary": "BTC halving cycle analysis supports YES outcome"
    }
  },
  {
    "type": "buy_yes",
    "market_id": 0,
    "timestamp": 1712345500,
    "block_number": 10,
    "tx_hash": "0x...",
    "details": {
      "usdc_in": "1000000000",
      "tokens_out": "995000000",
      "fee": "3000000",
      "is_yes": true
    }
  }
]
```

**检查点：**
- 按时间倒序排列（最新在前）
- 包含所有类型：`buy_yes`, `buy_no`, `sell`, `redeem`, `create_market`, `submit_evidence`
- 每条记录的 `tx_hash` 可在区块浏览器验证
- `details` 字段包含类型特定的详细信息

### 15c. 用户摘要

```bash
curl -s "http://localhost:8000/api/users/$TRADER_A/summary" | jq
```

**期望输出：**
```json
{
  "address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
  "active_positions": 1,
  "markets_created": 0,
  "evidence_submitted": 1,
  "total_value_usdc": "777400000"
}
```

### 15d. 部署者账户数据（同时是市场创建者）

```bash
DEPLOYER=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
curl -s "http://localhost:8000/api/users/$DEPLOYER/summary" | jq
```

**检查点：** `markets_created` 应 ≥ 1（部署者创建了市场）。

### 15e. 无活动用户

```bash
curl -s "http://localhost:8000/api/users/0x0000000000000000000000000000000000000001/positions" | jq
# 期望：[]

curl -s "http://localhost:8000/api/users/0x0000000000000000000000000000000000000001/transactions" | jq
# 期望：[]
```

---

## Step 16: 新增功能 — 卖出 Token（链上）

在 Step 5 买入后，交易者可以卖回 token：

```bash
TRADER_A_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
TRADER_A=0x70997970C51812dc3A010C7d01b50e0d17dc79C8

# 获取 YES token 地址
YES_TOKEN=$(cast call $MARKET "getMarketTokens(uint256)(address,address)" 0 --rpc-url http://localhost:8545 | head -1)

# 查看余额
cast call $YES_TOKEN "balanceOf(address)(uint256)" $TRADER_A --rpc-url http://localhost:8545

# 卖出部分 YES token（例如 500 个 token = 500000000）
cast send $MARKET "sell(uint256,bool,uint256)" 0 true 500000000 \
  --rpc-url http://localhost:8545 \
  --private-key $TRADER_A_KEY
```

**验证：**
```bash
# YES token 余额应减少
cast call $YES_TOKEN "balanceOf(address)(uint256)" $TRADER_A --rpc-url http://localhost:8545

# USDC 余额应增加
cast call $USDC "balanceOf(address)(uint256)" $TRADER_A --rpc-url http://localhost:8545

# 交易历史应新增一条 sell 记录
curl -s "http://localhost:8000/api/users/$TRADER_A/transactions" | jq '.[0]'
# 期望：type = "sell"
```

---

## Step 17: 前端新增功能验证

启动前端后，验证以下新功能：

| 页面 | 验证内容 |
|------|----------|
| **首页 — 分类标签** | 点击 "Crypto"/"Politics"/"Sports" 标签，市场列表只显示对应分类 |
| **首页 — 排序** | 切换 "Volume"/"Newest"/"Ending Soon" 排序，列表顺序变化 |
| **首页 — 搜索** | 输入 "BTC"，只显示包含 BTC 的市场 |
| **首页 — 统计栏** | 顶部显示总市场数、活跃数、总成交量、总证据数 |
| **首页 — 丰富卡片** | 市场卡片显示 YES%、成交量、证据数、状态指示器 |
| **市场详情 — 卖出** | 切换到 "Sell" tab，可选择卖 YES/NO，输入数量卖出 |
| **市场详情 — 活动** | 切换到 "Activity" tab，显示最近交易记录（交易者/类型/金额/时间） |
| **创建市场 — 分类** | 创建市场时可选择分类（Crypto/Politics/Sports/Tech/General） |
| **创建市场 — 解析来源** | 可输入 Polymarket 链接作为解析来源 |
| **创建市场 — 质押说明** | 显示 "50/50 AMM 拆分" 说明和金额计算 |
| **Portfolio — 持仓** | `/portfolio` 页面显示所有持仓市场、YES/NO 余额、当前价值 |
| **Portfolio — 历史** | "History" tab 显示所有交易记录、类型标签、tx hash、时间 |
| **Portfolio — 摘要** | 顶部显示总价值、活跃持仓数、创建市场数、证据提交数 |
| **Header** | 导航栏增加 "Portfolio" 链接 |

---

## 完整测试检查清单（更新版）

```
环境
  [ ] anvil 启动，端口 8545
  [ ] 合约部署成功，3 个地址记录
  [ ] 后端启动，/api/health 返回 chain_connected: true
  [ ] 前端启动，npm run build 成功

市场生命周期
  [ ] POST /api/markets 创建市场成功（含分类和解析来源）
  [ ] GET /api/markets 返回市场列表
  [ ] GET /api/markets/0 返回市场详情，priceYes ≈ 0.5

市场筛选/排序/搜索（NEW）
  [ ] ?category=crypto 只返回 Crypto 市场
  [ ] ?sort=volume 按成交量排序
  [ ] ?sort=newest 按创建时间排序
  [ ] ?sort=ending_soon 按截止时间排序
  [ ] ?search=BTC 只返回包含 BTC 的市场
  [ ] ?status=active 只返回活跃市场
  [ ] ?page=1&limit=2 分页正确
  [ ] 组合筛选正常工作

平台统计（NEW）
  [ ] GET /api/stats 返回正确的市场数、成交量、证据数

交易
  [ ] mint USDC 给交易者
  [ ] approve + buyYes 成功，YES 价格上升
  [ ] approve + buyNo 成功，YES 价格回落
  [ ] sell YES token 成功，USDC 余额增加
  [ ] 交易后 totalDeposited 增加

市场交易记录（NEW）
  [ ] GET /api/markets/0/trades 返回交易历史
  [ ] 交易记录按时间倒序
  [ ] type 正确（buy_yes/buy_no/sell_yes/sell_no）
  [ ] 每条记录含 tx_hash

证据
  [ ] POST /api/evidence/upload 返回 CID + hash
  [ ] submitEvidence 链上提交成功
  [ ] getEvidenceCount 返回 1
  [ ] hasEvidence 返回 true
  [ ] 后续交易手续费为 0.1%

AI 预测
  [ ] GET /api/predictions/0 返回概率 + 置信度 + 推理

结算 & 赎回
  [ ] evm_increaseTime 快进 31 天
  [ ] POST /api/markets/settle 结算成功
  [ ] resolved = true, outcome = true/false
  [ ] redeem 赎回成功，USDC 余额增加，token 归零

用户个人数据（NEW）
  [ ] GET /api/users/{addr}/positions 返回持仓列表
  [ ] 只返回有 token 的市场
  [ ] current_value_usdc 计算正确
  [ ] GET /api/users/{addr}/transactions 返回交易历史
  [ ] 按时间倒序，含所有类型
  [ ] GET /api/users/{addr}/summary 返回聚合数据
  [ ] 无活动用户返回空数据

Agent SDK
  [ ] pip install -e ./sdk 成功
  [ ] simple_trade.py 完成交易
  [ ] agent_trade.py 完成完整流程

前端新功能（NEW）
  [ ] 首页分类标签筛选正常
  [ ] 首页排序切换正常
  [ ] 首页搜索功能正常
  [ ] 首页统计栏数据正确
  [ ] 市场详情 Sell tab 可卖出 token
  [ ] 市场详情 Activity tab 显示交易记录
  [ ] 创建市场可选分类和填写解析来源
  [ ] Portfolio 页面持仓列表正确
  [ ] Portfolio 页面交易历史正确
  [ ] Portfolio 页面摘要数据正确
  [ ] Header 含 Portfolio 导航链接
```

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `chain_connected: false` | anvil 没有运行 | 确认 `anvil --port 8545` 在运行 |
| `'NoneType' object has no attribute 'functions'` | 合约地址未设置 | 检查环境变量 `PDX_MARKET_ADDRESS` 等 |
| `Method Not Allowed` | 后端未重启 | 用 `--reload` 启动或手动重启 |
| `execution reverted` on settle | 时间未到 deadline | 先运行 `evm_increaseTime` |
| `execution reverted` on buyYes | 未 approve USDC | 先 `cast send $USDC "approve(...)"` |
| `execution reverted: Locked` | 在锁仓期内交易 | deadline 前 30 分钟禁止交易 |
| MetaMask 连不上 | 网络未添加 | 添加 RPC `http://localhost:8545`, Chain ID `31337` |

---

# Part 2: Base Sepolia 测试网部署

以下流程部署到 Base Sepolia 真实测试网（Chain ID: 84532），验证合约、后端 API、MiroFish AI 分析、IPFS 证据系统在真实链上的完整运行。

---

## 前置条件

| 工具 | 用途 | 安装 |
|------|------|------|
| Foundry (forge, cast) | 合约编译/部署/调用 | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| Node.js >= 18 | 前端构建 | https://nodejs.org |
| Python >= 3.10 | 后端 API | https://python.org |
| MetaMask | 浏览器钱包（手动验证时） | https://metamask.io |

---

## Step T0: 获取测试网 ETH

部署合约和发送交易都需要 Base Sepolia ETH（无真实价值，免费领取）。

### 方式一：Alchemy Faucet（推荐）

- 地址: https://www.alchemy.com/faucets/base-sepolia
- 注册 Alchemy 账号（免费），每天可领 0.1 ETH
- 同时提供免费 RPC URL（部署合约需要）

### 方式二：Coinbase Developer Platform Faucet

- 地址: https://portal.cdp.coinbase.com/products/faucet
- 需注册 Coinbase Developer 账号（免费）
- 选择 "Base Sepolia" 网络，每天可领取

### 方式三：QuickNode Faucet

- 地址: https://faucet.quicknode.com/base/sepolia
- 注册 QuickNode 免费账号
- 支持 Base Sepolia 直接领取

### 方式四：Superchain Faucet（OP 官方）

- 地址: https://app.optimism.io/faucet
- Base 是 OP Stack 链，OP 官方水龙头直接支持 Base Sepolia
- 需要 GitHub 验证（>1 follower 或 >1 个 repo），无需注册

### 方式五：Chainlink Faucet

- 地址: https://faucets.chain.link/base-sepolia
- 需连接 MetaMask，支持 Base Sepolia
- 每次 0.1 ETH

### 方式六：Bware Labs Faucet

- 地址: https://bwarelabs.com/faucets/base-sepolia
- 无需注册，填入钱包地址即可

### 方式七：从 Sepolia 桥接

如果已有 Sepolia ETH，可以通过 Base 官方桥转到 Base Sepolia：
1. 先从 https://sepoliafaucet.com 或 https://faucets.chain.link/sepolia 领 Sepolia ETH
2. 打开 https://testnets.superbridge.app/base-sepolia
3. 从 Sepolia → Base Sepolia 桥接（约 1-2 分钟到账）

> **提示**: 建议从 2-3 个不同水龙头各领一些，以防某个水龙头暂停服务。
> 部署 + 完整 E2E 测试大约需要 **0.01 ETH**，领到 0.1 ETH 足够测试很多次。

### 关于 USDC

PDX 使用自部署的 **MockUSDC** 合约，部署时会自动给 deployer 铸造 1,000,000 USDC。
**不需要** 从任何水龙头获取 USDC。

---

## Step T1: 配置环境

### 合约 .env

```bash
cp contracts/.env.example contracts/.env
```

填入：
```bash
PRIVATE_KEY=0x你的私钥         # MetaMask 导出，仅测试网使用！
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/你的KEY
```

### 获取 RPC URL

| Provider | 免费额度 | 地址 |
|----------|---------|------|
| Alchemy | 300M compute units/月 | https://dashboard.alchemy.com |
| QuickNode | 50M API credits/月 | https://dashboard.quicknode.com |
| Infura | 100K requests/日 | https://app.infura.io |
| Ankr | 30 req/s 免费 | https://rpc.ankr.com/base_sepolia (无需注册) |
| PublicNode | 无需注册 | https://base-sepolia-rpc.publicnode.com |

> **最简方式**: 不想注册可直接用 `https://base-sepolia-rpc.publicnode.com` 或 `https://rpc.ankr.com/base_sepolia`（免费公共 RPC，适合测试）

---

## Step T2: 部署合约

```bash
# 一键完整流程：部署 → 验证 → 创建市场 → 交易 → 证据 → API → 前端 → 卖出
./e2e/testnet-deploy.sh

# 如果已部署过，跳过部署步骤：
./e2e/testnet-deploy.sh --skip-deploy
```

脚本会自动执行 8 个阶段（详见下方）。

### 手动部署（如需精细控制）

```bash
cd contracts

# 1. 运行单元测试
forge test --no-match-test "testFuzz"

# 2. 部署到 Base Sepolia
forge script script/Deploy.s.sol:DeployScript \
  --rpc-url $BASE_SEPOLIA_RPC_URL \
  --broadcast --slow

# 3. 记下输出的 3 个合约地址
#    MockUSDC:   0x...
#    PDXMarket:  0x...
#    PDXOracle:  0x...
```

---

## Step T3: 配置后端

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`：
```bash
RPC_URL=https://base-sepolia.g.alchemy.com/v2/你的KEY
CHAIN_ID=84532
PDX_MARKET_ADDRESS=0x...   # Step T2 部署得到
MOCK_USDC_ADDRESS=0x...    # Step T2 部署得到
PDX_ORACLE_ADDRESS=0x...   # Step T2 部署得到

# IPFS（可选，不配则用内存 mock）
PINATA_API_KEY=...
PINATA_SECRET_KEY=...

# MiroFish AI（可选，不配则用启发式分析）
USE_MOCK_MIROFISH=false
MIROFISH_LLM_API_KEY=sk-...
MIROFISH_LLM_BASE_URL=https://api.openai.com/v1
MIROFISH_LLM_MODEL=gpt-4o-mini
MIROFISH_INTERVAL_SECONDS=300
```

启动：
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Step T4: 配置前端

```bash
cd frontend
```

创建 `.env.local`：
```bash
VITE_CHAIN=testnet
VITE_RPC_URL=https://base-sepolia.g.alchemy.com/v2/你的KEY
VITE_PDX_MARKET_ADDRESS=0x...
VITE_MOCK_USDC_ADDRESS=0x...
```

构建或开发模式：
```bash
npm install
npm run dev        # 开发模式 → http://localhost:5173
npm run build      # 生产构建 → dist/
```

---

## Step T5: 在浏览器中手动测试

1. **MetaMask 配置**
   - 添加自定义网络：RPC `https://base-sepolia-rpc.publicnode.com`, Chain ID `84532`, Symbol `ETH`
   - 导入 deployer 私钥

2. **测试流程**
   - 打开 http://localhost:5173
   - 连接钱包
   - 创建市场 → Buy YES/NO → 提交证据 → 查看 MiroFish AI 分析 → 查看 Network 图
   - Portfolio 页面查看持仓和交易历史

3. **BaseScan 验证**
   - 打开 https://sepolia.basescan.org
   - 搜索 PDXMarket 地址查看链上交易记录

---

## 自动化 E2E 测试流程（8 阶段）

```
Phase 1: Prerequisites Check
  ├── 检查工具链 (forge, cast, python3, node)
  ├── 加载 contracts/.env
  └── 验证 deployer 有 ETH

Phase 2: Contract Deployment
  ├── 运行 forge test（先跑单元测试）
  ├── forge script Deploy.s.sol → Base Sepolia
  └── 提取合约地址

Phase 3: On-chain Verification
  ├── MockUSDC 合约响应检查
  ├── PDXMarket 合约响应检查
  ├── Oracle 地址正确性
  └── deployer USDC 余额

Phase 4: Create Sample Market
  ├── 创建示例市场
  ├── 读取 market question
  └── 验证 YES price > 0

Phase 5: Trading Test (Buy YES)
  ├── Approve USDC → PDXMarket
  ├── buyYes(0, 100 USDC)
  └── 验证价格上涨（AMM 生效）

Phase 6: Backend API + Evidence + MiroFish
  ├── GET /api/health
  ├── GET /api/markets + /api/markets/0
  ├── GET /api/predictions/0 (MiroFish AI 参考概率)
  ├── POST /api/evidence/upload (IPFS 上传)
  ├── cast submitEvidence (链上提交)
  ├── GET /api/evidence/0 (验证上链)
  ├── GET /api/evidence/0/0/content (IPFS 全文读取)
  ├── GET /api/predictions/topics/suggest (话题生成)
  ├── buyYes after evidence (0.1% 减免手续费)
  ├── GET /api/predictions/0 (含 amm_price_yes 对比)
  └── GET /api/markets/0/trades

Phase 7: Frontend Build Test
  ├── 配置 .env.local (testnet mode)
  └── npm run build → dist/index.html

Phase 8: Sell Test
  ├── 查询 YES token 余额
  ├── sellYes (卖回一半)
  └── 验证价格下降（AMM 反向生效）
```

---

## 完整数据流

```
用户提交证据
    │
    ├─→ POST /api/evidence/upload
    │     └─→ IPFS pin_json() → CID + bytes32 hash
    │           └─→ CID 注册到 _cid_registry
    │
    ├─→ cast submitEvidence(marketId, bytes32, summary)
    │     └─→ 链上存储: submitter + bytes32 + summary + timestamp
    │
    └─→ hasEvidence[user]=true → 下次交易手续费 0.1%

MiroFish 定时分析 (每5分钟)
    │
    ├─→ blockchain_service.list_markets() → 活跃市场
    ├─→ blockchain_service.get_evidence_list() → 链上证据列表
    ├─→ ipfs_service.fetch_by_hash(bytes32) → IPFS 全文内容
    │     包含: title, content, direction, sourceUrl
    │
    └─→ analyze_market(question, full_evidence)
          ├── LLM mode: 完整内容 + 方向 → prompt → 概率
          └── Heuristic: direction 权重 + 时间衰减 → 概率

前端展示
    ├─→ AMM 价格 → "Market Price" (真实成交价)
    ├─→ MiroFish → "AI Reference" (参考值, 仅供参考)
    └─→ Network Graph → 证据网络图 (证据节点 → AI 中心节点)
```

---

## 测试网常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `insufficient funds` | 测试 ETH 不够 | 去水龙头领，见 Step T0 |
| `could not connect` | RPC URL 错误 | 检查 Alchemy/QuickNode API key，或用公共 RPC |
| `nonce too low` | 之前的交易还没确认 | 等几秒重试 |
| Backend 504 | RPC 限流 | 换一个 RPC provider 或等一会儿 |
| Price 没变化 | 交易可能没上链 | 检查 BaseScan 上的 tx hash |
| IPFS content 404 | CID 注册在内存中，重启后丢失 | 重新上传证据或配置 Pinata |
| Topic suggest 返回默认值 | 没配置 LLM key | 设置 MIROFISH_LLM_API_KEY |
| 水龙头领不到 | 每日限额/IP 限制 | 换另一个水龙头（Step T0 列了 7 种） |

---

## 环境变量完整清单

```bash
# ── contracts/.env ──
PRIVATE_KEY=0x...
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY
MOCK_USDC=0x...      # 部署后填（用于 --skip-deploy）
PDX_MARKET=0x...     # 部署后填
PDX_ORACLE=0x...     # 部署后填

# ── backend/.env ──
RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY
CHAIN_ID=84532
PDX_MARKET_ADDRESS=0x...
MOCK_USDC_ADDRESS=0x...
PDX_ORACLE_ADDRESS=0x...
DEPLOYER_PRIVATE_KEY=0x...       # 后端用于发送交易
PINATA_API_KEY=...               # 可选
PINATA_SECRET_KEY=...            # 可选
PINATA_GATEWAY_URL=...           # 可选
USE_MOCK_MIROFISH=false          # false=启用真实分析
MIROFISH_LLM_API_KEY=sk-...     # 可选，空=启发式
MIROFISH_LLM_BASE_URL=https://api.openai.com/v1
MIROFISH_LLM_MODEL=gpt-4o-mini
MIROFISH_INTERVAL_SECONDS=300

# ── frontend/.env.local ──
VITE_CHAIN=testnet
VITE_RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY
VITE_PDX_MARKET_ADDRESS=0x...
VITE_MOCK_USDC_ADDRESS=0x...
```
