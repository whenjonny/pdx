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

1. 复制 `contracts/.env.example` 为 `contracts/.env`
2. 填入：

```bash
PRIVATE_KEY=0x你的私钥         # MetaMask 导出，仅测试网使用
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/你的KEY
```

3. 确保钱包有测试 ETH：https://www.alchemy.com/faucets/base-sepolia

## 运行

```bash
# 完整流程：部署合约 → 验证 → 创建市场 → 交易测试 → 后端 API 测试 → 前端构建
./e2e/testnet-deploy.sh

# 已有合约地址，跳过部署（需在 contracts/.env 中设置 MOCK_USDC, PDX_MARKET, PDX_ORACLE）
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
  ├── GET /api/markets
  ├── GET /api/markets/0
  ├── GET /api/predictions/0
  ├── GET /api/evidence/0
  └── GET /api/markets/0/trades

Phase 7: Frontend Build Test
  ├── 配置 .env.local (testnet mode)
  └── npm run build → dist/index.html

Phase 8: Sell Test
  ├── 查询 YES token 余额
  ├── sellYes (卖回一半)
  └── 验证价格下降（AMM 反向生效）
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
[OK]  Frontend build succeeded
[OK]  YES price decreased after sell (AMM working)

  Passed: 14
  Failed: 0
  All tests passed!
```

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `insufficient funds` | 测试 ETH 不够 | 去水龙头领：https://www.alchemy.com/faucets/base-sepolia |
| `could not connect` | RPC URL 错误 | 检查 Alchemy API key |
| `nonce too low` | 之前的交易还没确认 | 等几秒重试 |
| Backend 504 | RPC 限流 | 换一个 RPC provider 或等一会儿 |
| Price 没变化 | 交易可能没上链 | 检查 BaseScan 上的 tx hash |

## 手动验证

部署完成后，也可以手动在浏览器上验证：

1. 打开 https://sepolia.basescan.org
2. 搜索 PDXMarket 地址
3. Contract → Read Contract → `getPriceYes(0)` 查看价格
4. Contract → Write Contract → 连接 MetaMask 进行交易
