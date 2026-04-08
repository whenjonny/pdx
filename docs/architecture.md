# PDX 系统架构

> 证据驱动的 AI 预测市场：用户通过 AI Agent 提交证据并贡献算力参与 CPMM 市场，MiroFish 多智能体引擎聚合证据输出概率预测，结算锚定 Polymarket 结果。

---

## 架构总览

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

> 架构图亦可参见 [`ArchitectureDiagram_Simple.svg`](../ArchitectureDiagram_Simple.svg)

---

## 市场生命周期

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. MARKET CREATION                                              │
│   Market Creator → 选择 Polymarket topic                        │
│   → 部署 AMM 合约, deposit USDC 作为初始流动性                    │
│   → 设定 deadline (= Polymarket 到期时间 - 30min)                │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. PARTICIPATION (散户/机构 via AI Agents)                       │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Agent A  │  │ Agent B  │  │ Agent C  │  │ Human D  │        │
│  │ LLM+News │  │ Quant    │  │ Academic │  │ 手动交易  │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       ▼              ▼              ▼              ▼             │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              PDX AMM (Smart Contract)                │       │
│  │  buy/sell YES/NO tokens (CPMM: x * y = k)           │       │
│  │  可选: 附带 evidence → 获得手续费减免                   │       │
│  │  可选: 贡献算力 → 获得 Compute Credits                 │       │
│  └──────────────────────────────────────────────────────┘       │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. MIROFISH (多智能体预测引擎)                                    │
│                                                                 │
│  ┌─ 用户分布式计算 (免费, 本地 CPU) ──────────────────────┐      │
│  │  Embedding 生成  |  Monte Carlo  |  图算法  |  交叉验证 │      │
│  └────────────────────────┬──────────────────────────────┘      │
│                           ▼                                     │
│  ┌─ 中心协调 (LLM 最小化, 协议费覆盖) ──────────────────┐       │
│  │  Agent 仿真 (Top-K)  |  ReACT 报告生成  |  概率校准   │       │
│  └────────────────────────┬──────────────────────────────┘      │
│                           ▼                                     │
│            ┌───────────────────────┐                            │
│            │ 聚合概率: P(YES) = 72% │                            │
│            │ 置信度: HIGH           │                            │
│            └───────────────────────┘                            │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. LOCKDOWN + SETTLEMENT                                        │
│   deadline - 30min:  锁仓, 停止所有交易                           │
│   deadline:          等待 Polymarket 结果                         │
│   Polymarket resolve: Oracle 推送结果 → settle()                 │
│   redeem:            赢家兑换 USDC                                │
└─────────────────────────────────────────────────────────────────┘
```

### 时间线

```
t=0                                    t=deadline-30min    t=deadline
 │                                           │                │
 │  ◄──── Trading Phase ────►                │                │
 │                                           │                │
 ├── createMarket()                          ├── LOCKDOWN     ├── SETTLEMENT
 │   deposit USDC, 初始化 AMM                │   停止交易      │   Oracle 推送结果
 ├── 用户交易 buy/sell                        │   冻结仓位      │   settle() → redeem()
 ├── Agent 提交 evidence                     │   最终价格锁定   │
 ├── Agent 贡献算力                           │                │
 ├── MiroFish 持续更新概率                     │                │
 └───────────────────────────────────────────┘                │
```

---

## 智能合约设计

### PDXMarket.sol — 核心 AMM + Evidence

**CPMM (Constant Product Market Maker)**
- 二元市场：YES token + NO token
- 价格公式：`priceYes = reserveNo / (reserveYes + reserveNo)`
- 恒等式：`reserveYes * reserveNo = k`
- 初始流动性设定 50/50 赔率

```solidity
struct Market {
    string question;
    bytes32 polymarketConditionId;
    uint256 reserveYes;
    uint256 reserveNo;
    uint256 k;
    uint256 deadline;
    uint256 lockTime;        // = deadline - 30 minutes
    uint256 totalDeposited;
    bool resolved;
    bool outcome;            // true = YES wins
    address creator;
}

// Trading (锁仓前)
buyYes(marketId, usdcAmount, evidenceHash?)
buyNo(marketId, usdcAmount, evidenceHash?)
sell(marketId, isYes, tokenAmount)

// Evidence
submitEvidence(marketId, ipfsHash, summary)

// Settlement
settle(marketId, outcome)   // require(msg.sender == oracle)
redeem(marketId)            // 赢方 token 1:1 兑换 USDC
```

### 手续费与激励

| 条件 | 手续费 |
|------|--------|
| 无 evidence | 0.3% |
| 已提交 evidence | 0.1% |

手续费分配：60% LP 持有者 · 20% Evidence Pool · 10% Compute Pool · 10% 协议金库

### PDXOracle.sol — 结算

- 生产方案：Chainlink Functions 自动抓取 Polymarket 结果
- Demo 方案：owner 手动调用 `settle()`

### Token 设计

- YES / NO Token (ERC20)：每个 market 独立，由 PDXMarket 铸造/销毁
- 结算后：赢方 token = 1 USDC，输方 token = 0

---

## MiroFish 集成

MiroFish 是基于 OASIS 仿真引擎的多智能体 AI 预测引擎，在 PDX 中作为公共概率预测服务。

```
用户 AI Agent                      MiroFish
┌─────────────────────┐           ┌─────────────────────────┐
│ · 搜集证据            │  evidence │ · 聚合所有人的证据         │
│ · 本地计算 (embedding, │  ──────→ │ · 分布式任务协调           │
│   Monte Carlo, 图算法)│  compute  │ · 中心 LLM 推理 (仿真+报告)│
│ · 决定买卖方向        │           │ · 输出市场概率预测         │
│ · 执行交易            │  ←────── │ · 公开发布分析报告         │
│                      │  predict  │                         │
│ 一个用户一个 Agent    │           │ 一个市场一个 MiroFish 实例 │
└─────────────────────┘           └─────────────────────────┘
```

### 管线优化：分布式 + LLM 最小化

```
用户分布式 (本地 CPU, $0, ~70% 算力):
  Embedding 计算 → Monte Carlo → 图谱构建 → 图算法 → 统计模型 → 交叉验证

中心协调 (LLM, ~30% 算力, 协议费覆盖):
  Agent Persona 生成 → 关键决策仿真 → ReACT 报告 → 概率校准
```

成本对比：全中心化 $15-50/市场 → PDX 分布式 $1.5-5/市场（节省 ~90% LLM 成本）

---

## Evidence 系统

### 提交流程

1. Agent 搜集证据 (新闻/数据/分析)
2. 本地计算 embedding (sentence-transformers, 384 维)
3. 本地跑 Monte Carlo (5000+ 次模拟)
4. 上传到 IPFS via Pinata → 获得 CID
5. 调用 `PDXMarket.submitEvidence(marketId, ipfsHash, summary)`
6. MiroFish 监听事件，拉取分析，更新概率

### Evidence V2 格式 (IPFS)

```json
{
  "version": "1.0",
  "marketId": "0x...",
  "direction": "YES",
  "confidence": 0.75,
  "embedding": [0.12, -0.34, ...],
  "sources": [{ "url": "...", "title": "...", "credibility": 9.5 }],
  "analysis": "Based on recent data...",
  "compute_contributions": {
    "monte_carlo": { "n_sim": 5000, "mean": 0.72, "ci_95": [0.65, 0.79] }
  }
}
```

---

## 分布式算力

### 6 项可分布计算任务

| 任务 | 方法 | Credits |
|------|------|---------|
| Embedding 计算 | sentence-transformers (本地, ~50ms/条) | 1/条 |
| Monte Carlo | NumPy 随机采样 ×10K | 1/1000次 |
| 图算法 | PageRank, Louvain (networkx) | 5/次 |
| 统计模型 | Bayesian, ARIMA, Prophet | 3/模型 |
| 网页抓取 | requests + BeautifulSoup + spaCy NER | 2/URL |
| 交叉验证 | 事实三元组对比，数值检查 | 2/对 |

### Compute Credits 经济

- 10 credits = 1 次免手续费交易 (最高 100 USDC)
- 50 credits = 提前 1 小时查看 MiroFish 报告
- 100 credits = 兑换 0.5 USDC

### 防作弊

- 随机抽查 5% 提交，中心重算对比
- Embedding 验证：向量是否匹配文本
- Monte Carlo：分布合理性检查

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

## Agent SDK

```python
from pdx_sdk import PDXClient

client = PDXClient(
    rpc_url="https://base-sepolia.g.alchemy.com/v2/...",
    private_key="0x...",
    contract_address="0x...",
)

# 查看市场
market = client.get_market(market_id)

# 本地计算
embedding = client.compute_embedding(evidence_text)
mc = client.run_monte_carlo(market_id, n_sim=5000)

# 提交 evidence + 交易
client.submit_evidence(market_id, cid, "Key finding: ...")
client.buy_yes(market_id, usdc_amount=100, evidence_hash=cid)

# 结算后领取
client.redeem(market_id)
```

| 命令 | 功能 |
|------|------|
| `/pdx-markets` | 浏览所有活跃市场 |
| `/pdx-analyze <id>` | 深度分析：Web 搜索 + Embedding + Monte Carlo |
| `/pdx-submit <id> --direction YES\|NO` | 提交 V2 evidence → 生成签名链接 |
| `/pdx-trade <id> --amount <usdc>` | 生成买入签名链接 |
| `/pdx-portfolio` | 查看市场概况 |

---

## API 接口

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/markets` | 市场列表 |
| GET | `/api/markets/{id}` | 市场详情 |
| POST | `/api/markets` | 创建市场 |
| POST | `/api/markets/settle` | 结算市场 |
| POST | `/api/markets/mint-usdc` | Mint 测试 USDC |
| GET | `/api/evidence/{marketId}` | 证据列表 |
| POST | `/api/evidence/upload` | 上传证据到 IPFS |
| GET | `/api/predictions/{marketId}` | AI 预测 |
| GET | `/api/health` | 健康检查 |

完整 Swagger 文档：http://localhost:8000/docs

---

## 技术栈

| 层 | 技术 |
|----|------|
| 链 | Base L2 (Sepolia testnet) |
| 合约 | Solidity 0.8.x · Foundry · OpenZeppelin |
| Oracle | Chainlink Functions (生产) / Owner settle (demo) |
| AI 引擎 | MiroFish — 多智能体预测引擎 |
| 仿真 | OASIS (camel-ai/oasis) |
| Agent SDK | Python 3.12 · web3.py · sentence-transformers |
| 存储 | IPFS via Pinata · SQLite (本地持久化) |
| 后端 | Python 3.10+ · FastAPI · web3.py |
| 前端 | React 19 · TypeScript · Vite · wagmi · viem · Tailwind CSS |
| 测试代币 | MockUSDC (ERC20) |

---

## "Why Blockchain" 论证

| 问题 | 传统方案痛点 | 区块链解决方式 |
|------|-------------|--------------|
| 资金托管 | 中心化方需要信任, 可跑路 | AMM 合约自动托管 |
| 价格操纵 | 做市商可暗箱操作 | CPMM 公式链上透明 |
| 结算信任 | 结果可被篡改 | Oracle 结果不可逆 |
| 证据审计 | 证据可被删改/伪造 | IPFS hash 上链, 不可篡改 |
| AI 透明度 | 预测可被修改 | 预测记录上链, 可追溯 |
| 支付保证 | 赢家可能拿不到钱 | 智能合约自动兑付 |
| 开放参与 | 平台决定准入 | Permissionless |
| 算力贡献 | 中心独占算力价值 | Compute Credits 链上记账 |
