# PDX E2E Testnet Testing

Base Sepolia 测试链端到端测试流程。

## 前置条件

| 工具 | 用途 | 安装 |
|------|------|------|
| Foundry (forge, cast) | 合约编译/部署/调用 | https://getfoundry.sh |
| Node.js + npm | 前端构建 | https://nodejs.org |
| Python 3 | 后端 API | https://python.org |
| MetaMask | 浏览器钱包 | https://metamask.io |

## 配置

### 1. 合约配置

```bash
cp contracts/.env.example contracts/.env
```

填入：
```bash
PRIVATE_KEY=0x你的私钥         # MetaMask 导出，仅测试网使用
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/你的KEY
```

### 2. 获取测试 ETH（多种方式）

| 水龙头 | 地址 | 说明 |
|--------|------|------|
| Alchemy（推荐） | https://www.alchemy.com/faucets/base-sepolia | 注册免费，同时获得 RPC URL |
| Coinbase CDP | https://portal.cdp.coinbase.com/products/faucet | Coinbase 开发者平台 |
| QuickNode | https://faucet.quicknode.com/base/sepolia | 注册免费 |
| Superchain (OP) | https://app.optimism.io/faucet | 需 GitHub 验证，无需注册 |
| Chainlink | https://faucets.chain.link/base-sepolia | 连接 MetaMask 领取 |
| Bware Labs | https://bwarelabs.com/faucets/base-sepolia | 无需注册 |
| Sepolia→Base 桥接 | https://testnets.superbridge.app/base-sepolia | 先领 Sepolia ETH 再桥接 |

> MockUSDC 由合约自动铸造，**不需要** 从水龙头获取 USDC。

### 3. (可选) IPFS 配置

注册 https://www.pinata.cloud (免费)，拿到 API key。不配置则用 mock 模式。

### 4. (可选) LLM 配置

配置 OpenAI 兼容 API key，MiroFish 会用 LLM 分析证据。不配置则用启发式算法。

## 运行

```bash
# 完整流程：部署 → 验证 → 市场 → 交易 → 证据 → IPFS → API → 前端
./e2e/testnet-deploy.sh

# 已有合约地址，跳过部署
./e2e/testnet-deploy.sh --skip-deploy
```

## 测试流程（8 个阶段）

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
  ├── 创建示例市场（BTC $100K）
  ├── 读取 market question
  └── 验证 YES price > 0

Phase 5: Trading Test (Buy YES)
  ├── Approve USDC → PDXMarket
  ├── buyYes(0, 100 USDC)
  └── 验证价格上涨（AMM 生效）

Phase 6: Backend API Test
  ├── 启动 FastAPI 后端（连 Base Sepolia）
  ├── GET /api/health
  ├── GET /api/markets + /api/markets/0
  ├── GET /api/predictions/0 (MiroFish 参考概率)
  ├── POST /api/evidence/upload (IPFS 上传证据)
  ├── cast submitEvidence (链上提交证据)
  ├── GET /api/evidence/0 (验证证据上链)
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
    └─→ MiroFish → "AI Reference" (参考值, 仅供参考)
```

## 输出示例

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
[OK]  IPFS evidence content retrieved (direction=YES)
[OK]  Topic suggestions returned (5 topics)
[OK]  Post-evidence buyYes transaction submitted (0.1% fee)
[OK]  Frontend build succeeded
[OK]  YES price decreased after sell (AMM working)

  Passed: 21
  Failed: 0
  All tests passed!
```

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `insufficient funds` | 测试 ETH 不够 | 去水龙头领（见上方"获取测试 ETH"，7 种方式） |
| `could not connect` | RPC URL 错误 | 检查 Alchemy API key |
| `nonce too low` | 之前的交易还没确认 | 等几秒重试 |
| Backend 504 | RPC 限流 | 换一个 RPC provider 或等一会儿 |
| Price 没变化 | 交易可能没上链 | 检查 BaseScan 上的 tx hash |
| IPFS content 404 | CID 注册在内存中，重启后丢失 | 重新上传证据或配置 Pinata |
| Topic suggest 返回默认值 | 没配置 LLM key | 设置 MIROFISH_LLM_API_KEY |

## 手动浏览器验证

部署完成后，可以在浏览器上手动操作：

1. 打开 https://sepolia.basescan.org
2. 搜索 PDXMarket 地址
3. Contract → Read Contract → `getPriceYes(0)` 查看价格
4. Contract → Write Contract → 连接 MetaMask 进行交易

## 环境变量完整清单

```bash
# ── contracts/.env ──
PRIVATE_KEY=0x...
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY
MOCK_USDC=0x...      # 部署后填
PDX_MARKET=0x...     # 部署后填
PDX_ORACLE=0x...     # 部署后填

# ── backend/.env ──
RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY
CHAIN_ID=84532
PDX_MARKET_ADDRESS=0x...
MOCK_USDC_ADDRESS=0x...
PDX_ORACLE_ADDRESS=0x...
PINATA_API_KEY=...              # 可选
PINATA_SECRET_KEY=...           # 可选
USE_MOCK_MIROFISH=false         # false=启用真实分析
MIROFISH_LLM_API_KEY=sk-...    # 可选，空=启发式
MIROFISH_LLM_MODEL=gpt-4o-mini

# ── frontend/.env.local ──
VITE_CHAIN=testnet
VITE_RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY
VITE_PDX_MARKET_ADDRESS=0x...
VITE_MOCK_USDC_ADDRESS=0x...
```
