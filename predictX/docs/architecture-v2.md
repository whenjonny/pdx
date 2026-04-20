# PDX v2 — Evidence-Driven AI Prediction Market

## One-liner
证据驱动的 AI 预测市场：用户通过 AI Agent 提交证据并贡献算力参与 CPMM 市场，MiroFish 多智能体引擎聚合证据输出概率预测，结算锚定 Polymarket 结果。

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. MARKET CREATION                                              │
│                                                                 │
│   Market Creator (客户A)                                         │
│   → 选择 Polymarket topic (e.g. "Will X happen by 2026-06?")    │
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
│       │              │              │              │             │
│       ▼              ▼              ▼              ▼             │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              PDX AMM (Smart Contract)                │       │
│  │                                                      │       │
│  │  buy/sell YES/NO tokens (CPMM: x * y = k)           │       │
│  │  可选: 附带 evidence → 获得手续费减免                   │       │
│  │  可选: 贡献算力 → 获得 Compute Credits                 │       │
│  └──────────────────────┬───────────────────────────────┘       │
│                         │                                       │
│  Evidence (可选提交):    │  Compute (可选贡献):                   │
│  → IPFS hash + 元数据    │  → Embedding / Monte Carlo / 图算法   │
│  → 链上记录 evidenceHash │  → 结果提交到协调器                    │
└─────────────────────────┼───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. MIROFISH (多智能体预测引擎 — 分布式 + 中心协调)               │
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
│            公开发布 → 前端展示 / 链上记录                          │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. LOCKDOWN + SETTLEMENT                                        │
│                                                                 │
│   deadline - 30min:  锁仓, 停止所有交易                           │
│   deadline:          等待 Polymarket 结果                         │
│   Polymarket resolve: Oracle 推送结果 → settle()                 │
│   redeem:            赢家兑换 USDC                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Smart Contract Design (Solidity / Foundry / Base L2)

### PDXMarket.sol — 核心 AMM + Evidence

```solidity
struct Market {
    string question;              // 市场问题
    bytes32 polymarketConditionId;// 对应 Polymarket condition ID
    uint256 reserveYes;           // YES token 储备
    uint256 reserveNo;            // NO token 储备
    uint256 k;                    // 常数乘积
    uint256 deadline;             // 交易截止时间
    uint256 lockTime;             // = deadline - 30 minutes
    uint256 totalDeposited;       // 总存入 USDC
    bool resolved;
    bool outcome;                 // true = YES wins
    address creator;
}

struct Evidence {
    address submitter;
    bytes32 ipfsHash;             // IPFS CID of full evidence report
    string summary;               // 链上简短摘要 (< 256 bytes)
    uint256 timestamp;
    bytes32 marketId;
}

// === Market Lifecycle ===

createMarket(question, polymarketConditionId, deadline) payable
  → 存入 USDC 作为初始流动性
  → 初始化 50/50 池子 (reserveYes = reserveNo = deposit/2)
  → lockTime = deadline - 30 minutes
  → 铸造等量 YES + NO token

// === Trading (锁仓前) ===

buyYes(marketId, usdcAmount, evidenceHash?)
  → require(block.timestamp < market.lockTime)  // 锁仓检查
  → CPMM 定价: priceYes = reserveNo / (reserveYes + reserveNo)
  → 如果附带 evidenceHash: 手续费 0.1% (正常 0.3%)
  → 铸造 YES token 给用户

buyNo(marketId, usdcAmount, evidenceHash?)
  → 同上, 买 NO token

sell(marketId, isYes, tokenAmount)
  → require(block.timestamp < market.lockTime)
  → 卖回 token, 获得 USDC

// === Evidence (可选) ===

submitEvidence(marketId, ipfsHash, summary)
  → 记录 Evidence struct
  → emit EvidenceSubmitted(marketId, msg.sender, ipfsHash)
  → MiroFish 监听此事件, 拉取 IPFS 内容进行分析

// === Lockdown ===

// 自动生效: block.timestamp >= lockTime 后:
//   - buy/sell 全部 revert
//   - evidence 仍可提交 (不影响交易)
//   - 等待结算

// === Settlement ===

settle(marketId, outcome)
  → require(msg.sender == oracle)
  → require(block.timestamp >= market.deadline)
  → market.resolved = true
  → market.outcome = outcome

redeem(marketId)
  → require(market.resolved)
  → 赢方 token 按 1:1 兑换 USDC
  → 输方 token 价值归零
  → burn 用户的 YES/NO token
```

### PDXOracle.sol — Polymarket 结算桥

```
方案: Chainlink Functions

requestSettlement(marketId)
  → require(block.timestamp >= market.deadline)
  → Chainlink Functions 执行 JS:
     fetch(`https://gamma-api.polymarket.com/markets/${conditionId}`)
     → 解析 resolution: "YES" / "NO"
     → 回调 fulfillSettlement(marketId, outcome)

fulfillSettlement(marketId, outcome)
  → 调用 PDXMarket.settle(marketId, outcome)

Demo 备选:
  → owner 手动调用 settle(), 合约预留 oracle 接口
```

### Token 设计

```
YES Token (ERC20): PDXMarket 铸造/销毁, 每个 market 独立
NO Token (ERC20):  同上
LP Token:         内部记账 (mapping), 不做 ERC20

结算后:
  - 如果 outcome = YES: YES token = 1 USDC, NO token = 0
  - 如果 outcome = NO:  NO token = 1 USDC, YES token = 0
```

### 手续费与激励

```
正常交易手续费: 0.3% (swap 金额)
附带 evidence 的交易: 0.1%

手续费分配:
  - 60% → LP 持有者 (流动性提供激励)
  - 20% → Evidence Pool (奖励高质量证据)
  - 10% → Compute Pool (奖励算力贡献者)
  - 10% → 协议金库 (覆盖中心化 LLM 成本)

Evidence 额外奖励:
  - 如果 MiroFish 评定 evidence quality > 80: 额外 token 奖励
  - 如果提交的 evidence 方向与最终结果一致: 奖金加成

Compute Credits 奖励:
  - 贡献算力可获得 credits, 兑换手续费减免或 USDC
```

---

## Distributed Compute (分布式算力设计)

### 核心理念

MiroFish 的 LLM 调用成本高昂。通过将管线中非 LLM 的计算密集型任务分配给用户本地执行，可降低约 70% 的中心化成本，同时让用户成为预测引擎的算力贡献者。

### MiroFish 管线拆解: 哪些可以分布式

```
MiroFish 原始管线 (全中心化, LLM 重度):

  Stage 1        Stage 2          Stage 3           Stage 4
  Graph Build → Profile Gen →  Simulation     →  Report Gen
  (Zep+LLM)    (LLM×N实体)   (OASIS+LLM×N×轮)  (ReACT+LLM)
  ~10% 算力     ~15% 算力       ~55% 算力         ~20% 算力

PDX 优化管线 (分布式 + LLM 最小化):

  ┌─ 用户分布式 (本地 CPU, $0) ─────────────────────────────┐
  │                                                        │
  │  Stage 0: Evidence 采集     → Agent 爬取      [IO]     │
  │  Stage 1: Embedding 计算    → sentence-transformers    │
  │  Stage 2: 去重 + 聚类       → 向量相似度计算   [CPU]    │
  │  Stage 3: 图谱构建          → spaCy NER + 关系 [CPU]   │
  │  Stage 4: 图算法            → PageRank/社区    [CPU]   │
  │  Stage 5: Monte Carlo       → 概率模拟 ×10K   [CPU]   │
  │  Stage 6: 统计模型          → Bayesian/ARIMA   [CPU]   │
  │  Stage 7: 交叉验证          → 证据一致性对比   [CPU]    │
  │                                                        │
  │  → 占总有用计算 ~70%, LLM 成本 = $0                    │
  └────────────────────────┬───────────────────────────────┘
                           ▼
  ┌─ 中心协调 (LLM, 协议费覆盖) ───────────────────────────┐
  │                                                        │
  │  Agent Persona 生成   → LLM (但仅 Top-K 重要实体)      │
  │  关键决策仿真          → 精简 Agent 数, 减少轮次         │
  │  Report 综合推理       → LLM ReACT (基于已聚合数据)     │
  │  概率校准              → LLM 审核 Monte Carlo 结果      │
  │                                                        │
  │  → 占总计算 ~30%, 是最高价值的推理部分                   │
  │  → 成本由协议手续费覆盖                                 │
  └────────────────────────────────────────────────────────┘
```

### 6 项可分布计算任务详解

#### 1. Embedding 计算 (向量化)

```
用途: Evidence 语义去重, 聚类, 相似度搜索
模型: sentence-transformers/all-MiniLM-L6-v2 (本地, 免费, ~80MB)
计算: 每条 evidence ~50ms (CPU)

用户流程:
  1. 下载 evidence 文本
  2. 本地跑 embedding model → 输出 384 维向量
  3. 提交 (evidence_hash, embedding_vector) 到协调器
  4. 获得 1 Compute Credit / 条

成本对比:
  OpenAI embedding API: $0.0001/条, 1000条 = $0.10
  本地 sentence-transformers: $0, 1000条 ≈ 50秒 CPU
```

#### 2. Monte Carlo 概率模拟

```
用途: 基于 evidence 权重的概率分布估计
方法: 随机采样 → 加权计算 → 输出概率 + 置信区间
计算: 10K 次模拟 ≈ 2秒 (纯 NumPy)

用户流程:
  1. 下载当前 evidence pool + 权重矩阵
  2. 本地跑 N 次 Monte Carlo 模拟
  3. 提交: {mean, std, ci_95, n_simulations, raw_hash}
  4. 获得 1 Credit / 1000 次模拟

聚合: 中心收集所有用户模拟结果 → 加权平均 → 鲁棒概率估计
```

```python
# 示例: 纯 CPU, 零 LLM 成本
import numpy as np

def monte_carlo_predict(evidence_scores, weights, n_sim=10000):
    results = []
    for _ in range(n_sim):
        sampled_idx = np.random.choice(len(evidence_scores), size=len(evidence_scores), replace=True)
        sampled = evidence_scores[sampled_idx]
        w = weights[sampled_idx]
        prob = np.average(sampled, weights=w)
        results.append(prob)
    return {
        "mean": float(np.mean(results)),
        "std": float(np.std(results)),
        "ci_95": [float(np.percentile(results, 2.5)), float(np.percentile(results, 97.5))],
        "n_simulations": n_sim
    }
```

#### 3. Knowledge Graph 图算法

```
用途: 实体重要性排名, 社区发现, 信息传播路径
算法: PageRank, Louvain, Betweenness Centrality
工具: networkx / igraph (纯 Python, 本地)

用户流程:
  1. 下载图谱快照 (节点 + 边列表, JSON)
  2. 本地跑图算法
  3. 提交: {pagerank_scores, communities, key_paths}
  4. 获得 5 Credits / 次

用途举例:
  → PageRank 发现最有影响力的实体
  → 社区检测发现证据聚类
  → 最短路径发现因果链
```

#### 4. 统计 / 时序模型

```
用途: 基于历史数据的趋势预测
模型: Bayesian Updating, ARIMA, Prophet, Logistic Regression
工具: statsmodels, prophet, scikit-learn

用户流程:
  1. 获取市场历史价格 + 相关指标
  2. 本地拟合模型
  3. 提交: {model_type, forecast, features_used, r_squared}
  4. 获得 3 Credits / 模型
```

#### 5. 网页抓取 + 结构化解析

```
用途: Evidence 原始采集, 扩大信息面
方法: 爬取 URL → 提取文本 → NER 实体识别 → 结构化
工具: requests + BeautifulSoup + spaCy

用户流程:
  1. 领取待爬 URL 批次
  2. 本地抓取 + 解析 + NER
  3. 提交: {url, title, text, entities, publish_date}
  4. 获得 2 Credits / URL
```

#### 6. Evidence 交叉验证

```
用途: 检查证据间一致性, 发现矛盾
方法: 事实三元组对比, 数值范围检查, 时间线一致性
工具: 规则引擎 + 简单 NLP

用户流程:
  1. 下载 evidence pair (A, B)
  2. 本地对比: 事实是否矛盾? 数据是否一致?
  3. 提交: {pair_id, relation: "contradicts"|"supports"|"neutral", reasons}
  4. 获得 2 Credits / 对
```

### Compute Credits 经济模型

```
获取 Credits:
  Embedding 计算:    1 credit / 条 evidence
  Monte Carlo:       1 credit / 1000 次模拟
  图算法:            5 credits / 次
  统计模型:          3 credits / 模型
  网页抓取:          2 credits / URL
  交叉验证:          2 credits / evidence 对

消费 Credits:
  10 credits = 1 次免手续费交易 (最高 100 USDC)
  50 credits = 提前 1 小时查看 MiroFish 报告
  100 credits = 兑换 0.5 USDC (从协议金库)

防作弊:
  → 随机抽查: 中心重算 5% 的提交, 结果不一致则扣除 credits
  → Embedding 验证: 随机验证向量是否匹配文本
  → Monte Carlo: 检查分布是否合理 (不能全提交相同值)
```

### 成本对比

```
                    全中心化 MiroFish    PDX 分布式方案
  ─────────────────────────────────────────────────
  LLM API 调用       ~5000 次/市场        ~500 次/市场
  LLM 成本           $15-50/市场          $1.5-5/市场
  用户侧成本          $0                  ≈$0 (本地 CPU)
  节省                —                   ~90% LLM 成本
  额外收益            —                   用户获得 Credits
```

---

## MiroFish Integration (多智能体预测引擎)

### 角色定位

MiroFish (github.com/666ghj/MiroFish) 是基于 OASIS 仿真引擎的多智能体 AI 预测引擎。在 PDX 中作为**公共概率预测服务**，分布式执行轻量计算，集中执行高价值推理。

### 技术架构 (MiroFish 内部)

```
MiroFish 模块:
  backend/app/services/
  ├── graph_builder.py          ← Zep Cloud 知识图谱构建
  ├── ontology_generator.py     ← 本体/实体关系生成
  ├── oasis_profile_generator.py← Agent 人格档案生成 (LLM, 已支持并行)
  ├── simulation_ipc.py         ← 文件系统 IPC, Flask ↔ OASIS 仿真
  └── report_agent.py           ← ReACT 报告生成 (工具: insight_forge,
                                   panorama_search, quick_search, interview_agents)

依赖:
  ├── OASIS (camel-ai/oasis)    ← 社会仿真引擎 (Reddit + Twitter 双平台)
  ├── LLM API (OpenAI SDK 兼容) ← 推荐 qwen-plus (阿里百炼)
  └── Zep Cloud                 ← Agent 记忆图谱

管线: 种子信息 → 知识图谱 → Agent 人格生成 → 社会仿真演化 → 预测报告
```

### PDX 中的分工

```
用户 AI Agent                      MiroFish
┌─────────────────────┐           ┌─────────────────────────┐
│ 个人服务              │           │ 全市场公共服务             │
│                      │           │                         │
│ · 搜集证据            │  evidence │ · 聚合所有人的证据         │
│ · 本地计算 (embedding, │  ──────→ │ · 分布式任务协调           │
│   Monte Carlo, 图算法)│  compute  │ · 中心 LLM 推理 (仿真+报告)│
│ · 决定买卖方向        │           │ · 输出市场概率预测         │
│ · 执行交易            │  ←────── │ · 公开发布分析报告         │
│ · 提交 evidence 上链  │  predict  │                         │
│                      │           │                         │
│ 一个用户一个 Agent    │           │ 一个市场一个 MiroFish 实例 │
│ 利益: 个人收益最大化  │           │ 利益: 信息聚合最优化       │
└─────────────────────┘           └─────────────────────────┘
```

### MiroFish API (供前端和 Agent 调用)

```
GET  /api/markets/{marketId}/prediction
  → { probability: 0.72, confidence: "HIGH", lastUpdated: "..." }

GET  /api/markets/{marketId}/evidence
  → [{ submitter, ipfsHash, quality_score, summary, direction }]

GET  /api/markets/{marketId}/analysis
  → { reasoning: "...", key_factors: [...], risk_factors: [...] }

POST /api/compute/submit_embedding
  → { evidence_id, embedding_vector, credits_earned: 1 }

POST /api/compute/submit_montecarlo
  → { market_id, results: {mean, std, ci_95}, n_sim, credits_earned: 5 }

GET  /api/compute/tasks
  → [{ task_type, task_id, payload_url, credits_reward }]
```

---

## Market Lifecycle (时间线)

```
t=0                                    t=deadline-30min    t=deadline
 │                                           │                │
 │  ◄──── Trading Phase ────►                │                │
 │                                           │                │
 ├── createMarket()                          ├── LOCKDOWN     ├── SETTLEMENT
 │   deposit USDC                            │   停止交易      │   Oracle 推送结果
 │   初始化 AMM                               │   冻结仓位      │   settle()
 │                                           │   最终价格锁定   │   开放 redeem()
 ├── 用户交易 buy/sell                        │                │
 ├── Agent 提交 evidence                     │                │
 ├── Agent 贡献算力 (compute tasks)           │                │
 ├── MiroFish 持续更新概率                     │                │
 │                                           │                │
 │   AMM 价格随交易波动                        │                │
 │   MiroFish 概率随证据+算力更新              │                │
 └───────────────────────────────────────────┘                │
                                                              │
                                                     ┌───────┘
                                                     ▼
                                              Polymarket 结果
                                              → YES holders win
                                              → or NO holders win
                                              → redeem USDC
```

---

## Evidence System

### 提交流程

```
1. Agent 搜集证据 (新闻/数据/分析)
2. 本地计算 embedding (sentence-transformers)
3. 生成 evidence report (JSON)
4. 上传到 IPFS via Pinata → 获得 CID
5. 调用 PDXMarket.submitEvidence(marketId, ipfsHash, summary)
6. 链上记录 + emit 事件
7. 提交 embedding 到 MiroFish compute API
8. MiroFish 监听事件, 拉取分析, 更新概率
```

### Evidence 格式 (IPFS 存储)

```json
{
  "version": "1.0",
  "marketId": "0x...",
  "submitter": "0x...",
  "direction": "YES",
  "confidence": 0.75,
  "embedding": [0.12, -0.34, ...],
  "sources": [
    {
      "url": "https://reuters.com/...",
      "title": "...",
      "snippet": "...",
      "credibility": 9.5,
      "publishedDate": "2026-03-28"
    }
  ],
  "analysis": "Based on recent data from ...",
  "compute_contributions": {
    "monte_carlo": { "n_sim": 5000, "mean": 0.72, "ci_95": [0.65, 0.79] },
    "cross_validation": [{ "pair_id": "...", "relation": "supports" }]
  },
  "generatedBy": "claude-3.5-sonnet",
  "timestamp": "2026-04-02T10:30:00Z"
}
```

### 激励机制

```
提交 evidence 的好处:
  1. 交易手续费从 0.3% 降到 0.1%
  2. evidence quality > 80 (MiroFish 评分): 额外 token 奖励
  3. 方向正确 (与最终结果一致): 奖金池分成

贡献算力的好处:
  1. 获得 Compute Credits (可兑换手续费减免或 USDC)
  2. 提前查看 MiroFish 分析报告

不提交也可以交易:
  → 手续费 0.3%, 不参与 evidence/compute 奖励池
```

---

## Agent SDK (Python Package)

### 面向用户 Agent 开发者的 SDK

```python
from pdx_sdk import PDXClient

# 初始化
client = PDXClient(
    rpc_url="https://base-sepolia.g.alchemy.com/v2/...",
    private_key="0x...",
    contract_address="0x...",
)

# 查看市场
market = client.get_market(market_id)
print(f"Question: {market.question}")
print(f"YES price: {market.price_yes}")  # 0.65 = 65% implied probability
print(f"NO price:  {market.price_no}")   # 0.35

# 获取 MiroFish 预测
prediction = client.get_mirofish_prediction(market_id)
print(f"MiroFish says: {prediction.probability}")  # 0.72

# --- Evidence + Compute 流程 ---

# 搜集证据
evidence_data = client.search_evidence("reuters", market.question)

# 本地计算 embedding (免费, 本地 CPU)
embedding = client.compute_embedding(evidence_data["text"])

# 本地跑 Monte Carlo (免费, 本地 CPU)
mc_result = client.run_monte_carlo(market_id, n_sim=5000)

# 上传 evidence 到 IPFS
evidence_cid = client.upload_evidence_to_ipfs(evidence_data)

# 提交 evidence + 计算结果
tx = client.submit_evidence(market_id, evidence_cid, "Key finding: ...")
client.submit_compute(market_id, embedding=embedding, monte_carlo=mc_result)

# 交易 (附带 evidence 享受低手续费)
tx = client.buy_yes(market_id, usdc_amount=100, evidence_hash=evidence_cid)

# 领取 compute credits
credits = client.get_compute_credits()
print(f"Credits earned: {credits.total}")

# 结算后领取
tx = client.redeem(market_id)
```

---

## "Why Blockchain" 论证

| 问题 | 为什么传统数据库不行 | 区块链如何解决 |
|------|-------------------|--------------|
| 资金托管 | 中心化方需要信任, 可跑路 | AMM 合约自动托管, 代码即法律 |
| 价格操纵 | 做市商可暗箱操作 | CPMM 公式链上透明, 任何人可验证 |
| 结算信任 | 谁来判定结果? 可能被篡改 | Polymarket Oracle 结果不可逆 |
| 证据审计 | 证据可被删改/伪造 | IPFS hash 上链, 不可篡改 |
| AI 透明度 | 预测可以被修改 | 预测记录上链, 可追溯准确率 |
| 支付保证 | 赢家可能拿不到钱 | 智能合约自动兑付, 无需信任 |
| 开放参与 | 谁能参与由平台决定 | 任何人可部署 Agent, permissionless |
| 算力贡献 | 中心化平台独占算力价值 | Compute Credits 链上记账, 透明分配 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| 链 | Base L2 Sepolia testnet |
| 合约 | Solidity 0.8.x + Foundry + OpenZeppelin |
| Oracle | Chainlink Functions (生产) / Owner settle (demo) |
| AI 引擎 | MiroFish (github.com/666ghj/MiroFish) — 多智能体预测引擎 |
| 仿真核心 | OASIS (camel-ai/oasis) — 社会仿真 |
| 记忆图谱 | Zep Cloud — Agent 记忆 + 知识图谱 |
| Agent SDK | Python 3.12 + web3.py + sentence-transformers |
| 存储 | IPFS via Pinata (evidence) |
| 前端 | React + wagmi + viem |
| 测试代币 | MockUSDC (ERC20) |

---

## MVP 范围 (课程交付)

### Must Have (Week 12)
- [ ] PDXMarket.sol: createMarket, buyYes/No, sell, settle, redeem
- [ ] 锁仓逻辑: lockTime = deadline - 30min, 之后拒绝交易
- [ ] Evidence 提交: submitEvidence + IPFS 存储
- [ ] 手续费激励: 有 evidence 0.1%, 无 evidence 0.3%
- [ ] MockUSDC + YES/NO ERC20 token
- [ ] Agent SDK: Python package, 交易 + evidence + compute
- [ ] 分布式计算: 至少 embedding + Monte Carlo 两项
- [ ] MiroFish 集成: API 对接, 概率展示
- [ ] 前端: 连接钱包, 市场列表, 买卖, MiroFish 概率, 领取

### Nice to Have
- [ ] Chainlink Functions 自动结算
- [ ] 多市场并行
- [ ] Compute Credits 链上记账
- [ ] Agent 竞赛 dashboard (收益率 + 算力贡献排行)
- [ ] Evidence quality 自动评分 + 奖励分发
- [ ] MiroFish 概率历史图表
- [ ] LP 流动性管理 (addLiquidity / removeLiquidity)
- [ ] 图算法 + 交叉验证分布式任务

---

## 项目叙事 (Proposal Story)

```
Problem:
  预测市场 (Polymarket) 存在三大痛点:
  1. 冷启动流动性差 — 新市场无人做市
  2. 散户信息劣势 — 缺乏系统化分析能力
  3. AI 预测引擎成本高 — LLM 调用费用由平台独自承担

Solution:
  PDX = Evidence-Driven AI Prediction Market + Distributed Compute
  1. AMM (CPMM) 提供即时流动性 — 无需传统做市商
  2. 开放 Agent 生态 — 任何人可部署 AI Agent 参与
  3. Evidence 激励 — 提交证据降低手续费, 提升市场信息质量
  4. 分布式算力 — 用户贡献 CPU 跑 embedding/Monte Carlo/图算法
  5. MiroFish — 聚合证据 + 用户算力, 最小化 LLM 成本, 输出公共概率

Innovation:
  - "AI Agent 竞技场" — 多个独立 AI Agent 在预测市场中竞争
  - Evidence-backed trading — 交易不再是纯投机, 有证据支撑
  - Distributed AI Compute — 用户不只是交易者, 也是算力贡献者
  - MiroFish 作为公共品 — 70% 算力来自用户, 降低 90% LLM 成本

Why Blockchain:
  - Trustless 资金托管 (AMM)
  - 不可篡改的证据记录 (IPFS + 链上)
  - 自动化结算 (Oracle)
  - Permissionless 参与 (任何人可部署 Agent)
  - 透明的算力贡献记账 (Compute Credits)
```
