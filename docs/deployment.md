# PDX 测试网部署指南

完整部署流程：合约 → 后端 → 前端 → OpenClaw Agent。

目标网络：**Base Sepolia** (Chain ID: 84532)

---

## 前置准备

| 依赖 | 用途 | 获取方式 |
|------|------|----------|
| MetaMask | 钱包签名 | https://metamask.io |
| Alchemy 账号 | RPC 节点 | https://dashboard.alchemy.com |
| Base Sepolia ETH | Gas 费 | https://www.alchemy.com/faucets/base-sepolia |
| Foundry (forge/cast) | 合约编译部署 | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| Node.js 18+ | 前端构建 | https://nodejs.org |
| Python 3.10+ | 后端 + SDK | https://python.org |
| Pinata 账号 | IPFS 存储 | https://app.pinata.cloud (免费) |
| BaseScan API Key | 合约验证（可选） | https://basescan.org/apis |

### MetaMask 添加 Base Sepolia

| 字段 | 值 |
|------|----|
| Network Name | Base Sepolia |
| RPC URL | `https://sepolia.base.org` |
| Chain ID | `84532` |
| Currency | ETH |
| Explorer | `https://sepolia.basescan.org` |

---

## Phase 1: 部署合约

```bash
cd contracts
cp .env.example .env
```

编辑 `contracts/.env`：

```bash
PRIVATE_KEY=0x你的MetaMask私钥
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/你的key
BASESCAN_API_KEY=你的basescan_key    # 可选，用于 verify
```

部署三个合约（MockUSDC + PDXMarket + PDXOracle）：

```bash
source .env

forge script script/Deploy.s.sol:DeployScript \
  --rpc-url $BASE_SEPOLIA_RPC_URL \
  --broadcast \
  --verify
```

记录输出的地址：

```
MockUSDC deployed at:  0xAAAA...
PDXMarket deployed at: 0xBBBB...
PDXOracle deployed at: 0xCCCC...
```

创建示例市场（10,000 USDC 初始流动性）：

```bash
export MOCK_USDC=0xAAAA...
export PDX_MARKET=0xBBBB...

forge script script/CreateMarket.s.sol:CreateMarketScript \
  --rpc-url $BASE_SEPOLIA_RPC_URL \
  --broadcast
```

### 验证部署

```bash
# 检查合约是否响应
cast call $PDX_MARKET "marketCount()(uint256)" --rpc-url $BASE_SEPOLIA_RPC_URL
# 应返回 1

# BaseScan 查看
# https://sepolia.basescan.org/address/0xBBBB...
```

---

## Phase 2: 启动后端

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

# IPFS (Pinata)
PINATA_API_KEY=你的pinata_key
PINATA_SECRET_KEY=你的pinata_secret

# MiroFish 预测
USE_MOCK_MIROFISH=true              # 先用 mock，稳定后切 false
MIROFISH_LLM_API_KEY=sk-...         # OpenAI 兼容 key（mock 模式不需要）
MIROFISH_INTERVAL_SECONDS=300
```

启动：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

验证：

```bash
curl http://localhost:8000/api/health
# {"status":"ok","chain_id":84532,...}

curl http://localhost:8000/api/markets
# 返回市场列表
```

### 生产部署（可选）

使用 gunicorn 或部署到云服务：

```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

后端需要公网可访问，Agent 和前端都会调用 `/api/*` 接口。

---

## Phase 3: 启动前端

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

本地开发：

```bash
npm run dev
# http://localhost:5173
```

生产构建：

```bash
npm run build
# 输出到 frontend/dist/
```

### 部署到 Vercel

```bash
npm i -g vercel
cd frontend
vercel

# 在 Vercel Dashboard 设置环境变量：
# VITE_CHAIN=testnet
# VITE_RPC_URL=...
# VITE_PDX_MARKET_ADDRESS=...
# VITE_MOCK_USDC_ADDRESS=...
```

前端必须公网可访问 —— Agent 生成的 `/sign` 签名链接需要用户在浏览器中打开。

---

## Phase 4: 安装 OpenClaw Agent 插件

### 安装 SDK

```bash
cd sdk
pip install -e .

# 验证
python3 -c "from pdx_sdk.signing import build_buy_url; print('OK')"
```

### 设置环境变量

```bash
export PDX_BACKEND_URL="http://localhost:8000"       # 后端地址
export PDX_FRONTEND_URL="http://localhost:5173"       # 前端地址（或 Vercel 公网 URL）
```

如果前端部署到了公网（例如 `https://pdx.vercel.app`），则：

```bash
export PDX_FRONTEND_URL="https://pdx.vercel.app"
```

### 在 Claude Code 中使用

```bash
# 方式 1：直接引用 skill 目录
claude --skill ./skill

# 方式 2：复制到全局 skills 目录
cp -r skill/ ~/.claude/skills/pdx-predict/
```

### 可用命令

| 命令 | 功能 |
|------|------|
| `/pdx-markets` | 浏览所有活跃市场 |
| `/pdx-analyze <market_id>` | 深度分析：Web 搜索 + Embedding + Monte Carlo |
| `/pdx-submit <market_id> --direction YES\|NO` | 提交 V2 evidence 到 IPFS → 生成签名链接 |
| `/pdx-trade <market_id> --amount <usdc>` | 生成买入签名链接 |
| `/pdx-portfolio` | 查看市场概况 |

---

## Phase 5: 端到端验证

### 完整流程测试

```
1. Agent: /pdx-markets
   → 显示市场列表、价格、MiroFish 概率

2. Agent: /pdx-analyze 1
   → Web 搜索收集证据
   → 本地计算 embedding (384-dim) + Monte Carlo (5000 sims)
   → 输出分析报告 + 交易建议

3. Agent: /pdx-submit 1 --direction YES
   → 打包 V2 evidence (embedding + MC + structured analysis)
   → 上传 IPFS → 获取 CID
   → 生成签名链接：
     https://pdx.vercel.app/sign?action=submitEvidence&marketId=1&direction=YES&ipfsHash=0x...

4. 用户点击链接
   → /sign 页面打开，显示交易摘要
   → MetaMask 弹出，用户确认
   → Evidence 提交上链，解锁 0.10% 手续费

5. Agent: /pdx-trade 1 --amount 100
   → 生成签名链接：
     https://pdx.vercel.app/sign?action=buyYes&marketId=1&amount=100&direction=YES

6. 用户点击链接
   → /sign 页面检查 USDC 授权（不足则先 approve）
   → MetaMask 弹出 1-2 次，用户确认
   → 交易完成，获得 YES tokens
```

### 自动化 E2E 测试

```bash
cd e2e
bash testnet-deploy.sh
```

8 个阶段自动执行：环境检查 → 合约部署 → 链上验证 → 创市场 → 买入测试 → API 测试 → 前端构建 → 卖出测试。

---

## 安全模型

```
Agent 可以做的：                    Agent 不能做的：
─────────────────                  ─────────────────
- 读市场数据（公开）                 - 签名交易
- Web 搜索收集证据                  - 访问私钥
- 本地计算 embedding               - 转移资金
- 本地跑 Monte Carlo               - 执行交易
- 上传 evidence 到 IPFS            - 授权代币
- 生成签名 URL                     - 访问用户钱包
```

所有链上操作通过前端 `/sign` 页面完成，用户在 MetaMask 中审查并确认每笔交易。

---

## 架构图

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  AI Agent        │     │  Backend (8000)   │     │  Base Sepolia    │
│  (Claude Code)   │     │  FastAPI          │     │  Chain ID 84532  │
│                  │     │                   │     │                  │
│  /pdx-analyze    │────→│  /api/markets     │────→│  PDXMarket       │
│  /pdx-submit     │────→│  /api/evidence/*  │     │  MockUSDC        │
│  /pdx-trade      │     │  /api/predictions │     │  PDXOracle       │
│                  │     │                   │     │                  │
│  embedding +     │     │  MiroFish V2      │     │                  │
│  Monte Carlo     │     │  Aggregator       │     │                  │
│  (local CPU)     │     │  (incremental)    │     │                  │
└────────┬─────────┘     └──────────────────┘     └──────────────────┘
         │
         │ 生成签名 URL
         ▼
┌──────────────────┐     ┌──────────────────┐
│  Frontend (5173) │     │  IPFS (Pinata)   │
│  React + Vite    │     │                  │
│                  │     │  V2 Evidence     │
│  /sign 页面      │     │  - embedding     │
│  MetaMask 签名   │     │  - monteCarlo    │
│  自动 approve    │     │  - sources       │
└──────────────────┘     └──────────────────┘
```

---

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| `forge script` 报 gas 不足 | 到 Alchemy faucet 领取更多 Base Sepolia ETH |
| MetaMask 不弹出 | 确认浏览器已安装 MetaMask 并解锁，网络切到 Base Sepolia |
| `/sign` 页面白屏 | 检查 `VITE_PDX_MARKET_ADDRESS` 是否正确设置 |
| IPFS 上传失败 | 检查 Pinata API key 是否有效 |
| Agent 生成的链接打不开 | 确认 `PDX_FRONTEND_URL` 指向正确的前端地址 |
| MiroFish 不更新预测 | 检查 `USE_MOCK_MIROFISH` 设置，确认后端日志 |
| `sentence-transformers` 安装慢 | `pip install sentence-transformers --no-deps` 然后手动装依赖 |
| 合约 verify 失败 | 确认 `BASESCAN_API_KEY` 正确，或手动到 BaseScan 提交源码 |
