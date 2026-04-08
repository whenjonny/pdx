# PDX 安装指引

## 前置条件

| 工具 | 用途 | 获取方式 |
|------|------|----------|
| [Foundry](https://getfoundry.sh/) (forge, anvil, cast) | 合约编译/部署/调用 | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| [Node.js](https://nodejs.org/) >= 18 | 前端构建 | https://nodejs.org |
| Python >= 3.10 | 后端 + SDK | https://python.org |
| MetaMask（测试网需要） | 浏览器钱包签名 | https://metamask.io |

---

## 快速启动（一键 Demo）

```bash
./scripts/demo-setup.sh
```

自动启动本地链、部署合约、创建示例市场、启动后端和前端。打开 http://localhost:5173 即可使用。

---

## 手动安装（本地开发）

### 1. 启动本地链

```bash
anvil --port 8545 --chain-id 31337 --block-time 1
```

保持运行。Anvil 会预置 10 个测试账户，每个有 10,000 ETH。

### 2. 部署合约

```bash
cd contracts
forge script script/Deploy.s.sol:DeployScript \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --broadcast
```

记下输出的 3 个地址：MockUSDC、PDXMarket、PDXOracle。

### 3. 启动后端

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

### 4. 启动前端

```bash
cd frontend
npm install
echo "VITE_CHAIN=local
VITE_PDX_MARKET_ADDRESS=0x...
VITE_MOCK_USDC_ADDRESS=0x..." > .env.local
npm run dev
```

打开 http://localhost:5173。

---

## 测试网部署（Base Sepolia）

目标网络：**Base Sepolia** (Chain ID: 84532)

### 额外依赖

| 依赖 | 用途 | 获取方式 |
|------|------|----------|
| Alchemy 账号 | RPC 节点 | https://dashboard.alchemy.com |
| Base Sepolia ETH | Gas 费 | 见下方水龙头列表 |
| Pinata 账号（可选） | IPFS 存储 | https://app.pinata.cloud |
| BaseScan API Key（可选） | 合约验证 | https://basescan.org/apis |

### 获取测试 ETH

| 水龙头 | 地址 | 说明 |
|--------|------|------|
| Alchemy（推荐） | https://www.alchemy.com/faucets/base-sepolia | 注册免费，同时获得 RPC URL |
| Coinbase CDP | https://portal.cdp.coinbase.com/products/faucet | Coinbase 开发者平台 |
| QuickNode | https://faucet.quicknode.com/base/sepolia | 注册免费 |
| Superchain (OP) | https://app.optimism.io/faucet | 需 GitHub 验证 |
| Chainlink | https://faucets.chain.link/base-sepolia | 连接 MetaMask 领取 |
| Bware Labs | https://bwarelabs.com/faucets/base-sepolia | 无需注册 |
| Sepolia→Base 桥接 | https://testnets.superbridge.app/base-sepolia | 先领 Sepolia ETH 再桥接 |

> MockUSDC 由合约自动铸造，**不需要** 从水龙头获取 USDC。

### MetaMask 添加 Base Sepolia

| 字段 | 值 |
|------|----|
| Network Name | Base Sepolia |
| RPC URL | `https://sepolia.base.org` |
| Chain ID | `84532` |
| Currency | ETH |
| Explorer | `https://sepolia.basescan.org` |

### Phase 1: 部署合约

```bash
cd contracts
cp .env.example .env
```

编辑 `contracts/.env`：

```bash
PRIVATE_KEY=0x你的MetaMask私钥
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/你的key
BASESCAN_API_KEY=你的basescan_key    # 可选
```

部署：

```bash
source .env
forge script script/Deploy.s.sol:DeployScript \
  --rpc-url $BASE_SEPOLIA_RPC_URL \
  --broadcast --verify
```

记录输出地址，创建示例市场：

```bash
export MOCK_USDC=0xAAAA...
export PDX_MARKET=0xBBBB...
forge script script/CreateMarket.s.sol:CreateMarketScript \
  --rpc-url $BASE_SEPOLIA_RPC_URL --broadcast
```

### Phase 2: 启动后端

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`：

```bash
RPC_URL=https://base-sepolia.g.alchemy.com/v2/你的key
CHAIN_ID=84532
PDX_MARKET_ADDRESS=0xBBBB...
MOCK_USDC_ADDRESS=0xAAAA...
PDX_ORACLE_ADDRESS=0xCCCC...
DEPLOYER_PRIVATE_KEY=0x你的私钥
PINATA_API_KEY=你的pinata_key          # 可选
PINATA_SECRET_KEY=你的pinata_secret     # 可选
USE_MOCK_MIROFISH=true
```

启动：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Phase 3: 启动前端

```bash
cd frontend
npm install
```

创建 `.env.local`：

```bash
VITE_CHAIN=testnet
VITE_RPC_URL=https://base-sepolia.g.alchemy.com/v2/你的key
VITE_PDX_MARKET_ADDRESS=0xBBBB...
VITE_MOCK_USDC_ADDRESS=0xAAAA...
```

```bash
npm run dev          # 开发模式
npm run build        # 生产构建 → frontend/dist/
```

### Phase 4: 安装 OpenClaw Agent 插件

```bash
cd sdk
pip install -e .
python3 -c "from pdx_sdk.signing import build_buy_url; print('OK')"
```

设置环境变量：

```bash
export PDX_BACKEND_URL="http://localhost:8000"
export PDX_FRONTEND_URL="http://localhost:5173"  # 或 Vercel 公网 URL
```

在 Claude Code 中使用：

```bash
claude --skill ./skill
```

---

## 环境变量完整清单

```bash
# ── contracts/.env ──
PRIVATE_KEY=0x...
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY

# ── backend/.env ──
RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY
CHAIN_ID=84532                         # 31337 for local
PDX_MARKET_ADDRESS=0x...
MOCK_USDC_ADDRESS=0x...
PDX_ORACLE_ADDRESS=0x...
DEPLOYER_PRIVATE_KEY=0x...             # 测试网需要
PINATA_API_KEY=...                     # 可选
PINATA_SECRET_KEY=...                  # 可选
USE_MOCK_MIROFISH=true                 # false=启用真实分析
MIROFISH_LLM_API_KEY=sk-...           # 可选
MIROFISH_LLM_MODEL=gpt-4o-mini
DEPLOY_BLOCK=0                         # 合约部署时的区块号

# ── frontend/.env.local ──
VITE_CHAIN=testnet                     # local / testnet
VITE_RPC_URL=https://base-sepolia.g.alchemy.com/v2/KEY
VITE_PDX_MARKET_ADDRESS=0x...
VITE_MOCK_USDC_ADDRESS=0x...
```

---

## 常用命令

```bash
# 合约
forge build                    # 编译
forge test -vvv                # 单元测试
forge script script/Deploy.s.sol:DeployScript --rpc-url <url> --private-key <key> --broadcast

# 后端
uvicorn app.main:app --port 8000 --reload

# 前端
npm run dev                    # 开发服务器 (5173)
npm run build                  # 生产构建

# SDK
pip install -e ./sdk
python sdk/examples/agent_trade.py

# 全栈一键启动
./scripts/demo-setup.sh
```
