# 预测市场竞品分析 (Prediction Market Competitive Analysis)

**CONVERTOTC-7902 | Supplementary Research**
**Date:** February 25, 2026
**Status:** Complete

---

## Executive Summary

预测市场在 2025 年经历爆发式增长，全球交易量超过 $44B（YoY 400%+），2026 年有望突破 $100-325B。市场已形成 **Polymarket + Kalshi 双寡头格局**（占 85-90% 份额），但竞争正在急剧加速——2025-2026 年间，Robinhood、Coinbase、CME、Gemini、Interactive Brokers、Kraken、Cboe 等主流金融机构密集入场。

**关键发现：**
- Robinhood 是交易量最大的分发渠道（2025 年 120 亿+ 合约）
- CME 上线仅 8 周即达 1 亿合约
- BNB Chain 生态已有 Opinion Lab（$8B+/月）和 predict.fun 等布局
- 两种主要入场模式：**合作 Kalshi**（Coinbase、Webull）vs **自建/收购 DCM 牌照**（Robinhood、Kraken、Gemini）
- 非美国交易所（OKX、Bybit）因监管复杂性尚未进入
- **Binance 存在明显的窗口期，但窗口正在关闭**

---

## 1. 市场格局总览

### 1.1 市场份额（2025-2026 Weekly Data）

| 平台 | 周交易量（Feb 2026） | 市场份额 | 类型 |
|------|---------------------|----------|------|
| **Kalshi** | ~$2.59B | ~49% | 中心化/CFTC DCM |
| **Polymarket** | ~$1.82B | ~35% | 去中心化/Polygon |
| **其他（含 BNB Chain）** | ~$0.85B | ~16% | 混合 |

### 1.2 年度交易量趋势

| 年份 | 全球预测市场交易量 | YoY 增长 |
|------|-------------------|----------|
| 2023 | <$1B | - |
| 2024 | ~$9B | >900% |
| 2025 | ~$44B | ~400% |
| 2026E | $100-325B | 125-640% |

---

## 2. TIER 1: 纯预测市场平台

### 2.1 Polymarket — 链上预测市场领导者

| 维度 | 详情 |
|------|------|
| **成立** | 2020，创始人 Shayne Coplan |
| **总部** | 纽约 |
| **链** | Polygon (L2)，USDC 结算 |
| **订单匹配** | 混合 CLOB（链下匹配，链上结算） |
| **预言机** | UMA Optimistic Oracle + Chainlink Data Streams |
| **融资** | $2.3B+（Founders Fund, ICE $2B, Paradigm, Sequoia） |
| **估值** | $11.6B（Jan 2026），传闻 $12-15B 新轮 |
| **2025 交易量** | ~$21.5B |
| **Jan 2026 月交易量** | $7.66B |
| **活跃交易者** | 477,000+（Oct 2025） |
| **市场数量** | 8,000+ |
| **费率** | 0%（计划美国市场 1bp taker fee） |
| **监管** | 收购 QCEX 获 CFTC 牌照，2025 年底重返美国 |
| **Token** | POLY（2026 年中 TGE 预期） |

**市场类别：** 政治、体育、加密、经济、流行文化、科技、科学

**核心优势：**
- 全球最深的链上预测市场流动性
- 零手续费模型吸引大量交易量
- 媒体品牌认知度最高（被主流媒体引用为概率参考）
- ICE（NYSE 母公司）$2B 战略投资背书
- 加密原生用户群

**核心劣势：**
- Oracle 争议事件（UMA dispute 解决机制受质疑）
- 用户集中度高（少数高频交易者贡献大量交易量）
- 盈利模式待验证（从 VC 补贴向收费过渡中）
- 美国市场信任仍在重建中（2022 年 CFTC 罚款 $1.4M）

---

### 2.2 Kalshi — CFTC 监管的预测交易所

| 维度 | 详情 |
|------|------|
| **成立** | 2018，MIT 毕业生 Tarek Mansour & Luana Lopes Lara |
| **总部** | 纽约 |
| **类型** | 中心化，CFTC Designated Contract Market (DCM) |
| **融资** | ~$1.59B（Paradigm, Bond Capital, Sequoia, SV Angel） |
| **估值** | $11B（Series E, late 2025） |
| **2025 交易量** | $23.8B（+1,100% YoY） |
| **2025 交易笔数** | 9700 万（+1,680% YoY） |
| **Jan 2026 交易量** | $9.55B / 5450 万笔 |
| **Super Bowl 单日记录** | >$1B（Feb 2026） |
| **费率** | ~1% effective take rate，cap $1.74/100 |
| **费收入（90天 est.）** | ~$15.2M |
| **做市商** | Susquehanna (SIG) 为 designated MM |
| **市场数量** | 1,200+ |

**市场类别：** 体育（~87% 交易量）、政治、经济、天气、娱乐

**核心优势：**
- 唯一拥有 CFTC DCM 牌照的专业预测交易所
- 法币入金（ACH/debit/wire）——非加密用户可直接参与
- 体育高频交易基建成熟
- 机构级合作（Tradeweb, Robinhood, SIG）
- 已验证的收入模型

**核心劣势：**
- 仅限美国市场
- 高度依赖体育交易量（~87%）——集中风险
- 费率高于 Polymarket（1% vs 0%）
- CFTC 关于政治合约的上诉仍在进行
- 州级监管不确定性

---

### 2.3 其他纯预测市场平台

| 平台 | 链 | 状态 | 2025 交易量 | 融资 | 特点 |
|------|-----|------|------------|------|------|
| **PredictIt** | 无（中心化） | 2025/9 重新上线 | 未公开 | 私有 | CFTC DCM+DCO 双牌照；历史品牌；提高交易限额至 $3,500 |
| **Limitless** | Base (Coinbase L2) | 活跃 | $497M+ 累计 | 未公开 | CLOB 模式；专注短期资产价格预测（时/日级别） |
| **Overtime Markets** | Optimism/Arbitrum | 活跃 | $362M+ 累计 | 未公开 | 原 Thales 改名；$OVER token；去中心化体育博彩 |
| **Drift BET** | Solana | 活跃（事件驱动） | 未公开 | $52.5M（母公司） | Solana DeFi 生态集成；Pyth 预言机 |
| **Azuro** | Multi-EVM | 活跃 | 未公开 | $11M | B2B 基础设施层；多前端应用 |
| **Futuur** | Arbitrum/Web | 活跃 | 极小 | 自筹 | 法币+加密双模式；Curacao 牌照 |
| **Hedgehog** | Solana | 边缘化 | 极小 | $3.5M | 零损失竞赛特色；不对美国开放 |
| **Metaculus** | 无 | 活跃 | N/A（无真金） | ~$8.7M（grants） | 预测平台非交易市场；Bridgewater 合作 |
| **Manifold** | 无 | 衰退中 | N/A（虚拟币） | 未公开 | DAU 从 2000+ 降至 886；放弃真金交易 |
| **Augur** | Ethereum | 实质休眠 | ~$0 | $5.3M (ICO) | 2025/3 宣布 "重启" 转型为预言机基础设施 |

---

## 3. TIER 2: 主流交易所/金融机构入场

### 3.1 竞争格局总览

| 交易所 | 入场时间 | 入场模式 | 交易量数据 | 费率 | 监管方式 |
|--------|---------|---------|-----------|------|---------|
| **Robinhood** | Early 2025 | 合作→自建（收购 MIAXdx） | **120亿+ 合约/2025**；34亿/Jan 2026 | $0.01/合约 | JV with SIG 收购 DCM |
| **Coinbase** | Jan 28, 2026 | 合作 Kalshi + 收购 Clearing Co. | 未公开（上线 4 周） | 含在交易价格中 | 通过 Kalshi DCM |
| **CME Group** | Dec 2025 | 自建 + FanDuel 合作 | **8 周达 1 亿合约** | 未详 | 已有 DCM |
| **Gemini** | Dec 2025 | 自建（新获 DCM 牌照） | 未公开 | 未详 | 自有 DCM |
| **Interactive Brokers** | Jul 2024 | 自建 ForecastEx（自有 DCM+DCO） | 未公开 | **免佣金 + 利息激励** | 自有 DCM+DCO |
| **Webull** | Q3 2025 | 合作 Kalshi | 未公开 | 零佣金（交易所费另计） | 通过 Kalshi DCM |
| **Crypto.com** | 2025 | 自建 CDNA | 未公开 | 未详 | 自有 DCM (CDNA) |
| **Kraken** | 计划 2026 | 收购 Small Exchange ($100M) | N/A | N/A | 收购 DCM |
| **Cboe** | 计划 mid-2026 | 自建 | N/A | N/A | SEC 监管（非 CFTC） |
| **dYdX** | 2025 | DeFi 原生 | 未公开 | 质押者减免 | 去中心化 |
| **OKX** | 未入场 | - | - | - | - |
| **Bybit** | 未入场 | 探索合作中 | - | - | - |

### 3.2 重点竞争对手详解

#### Robinhood — 交易量冠军

**关键数据：**
- 2025 全年：**120 亿+** 事件合约交易
- Q4 2025：85 亿合约（QoQ +270%）
- Jan 2026：34 亿合约（MoM +17%）
- Q4 2025 "其他交易收入"：**$1.47 亿**（YoY +300%+）
- 事件合约是 Robinhood **增长最快的收入线**

**战略路径：** 合作→自建
1. 初期通过 Kalshi 合作快速上线
2. 2025/11 与 Susquehanna (SIG) 成立 JV
3. 2026/1 完成收购 MIAXdx 90% 股权（CFTC DCM 牌照）
4. 计划在 MIAXdx 基础上建设自有衍生品交易所

**核心优势：** 最大零售用户分发能力；SIG 做市提供流动性深度；最激进的增长策略
**核心劣势：** 主要面向散户；尚未形成独立交易所运营经验

#### Coinbase — 双轨战略

**入场方式：** 合作 + 收购
- 2025/12 收购 The Clearing Company（预测市场基建初创）
  - 创始人 Toni Gemayel 来自 Kalshi 和 Polymarket
  - 该公司已向 CFTC 申请运营稳定币原生清算所
- 2026/1/28 上线 "Coinbase Predictions"（通过 Kalshi）
- 全 50 州可用，支持 USDC 结算

**战略定位：** "Everything Exchange"——同一 App 内提供加密、股票/ETF、预测市场。收购 Clearing Company 表明不会长期依赖 Kalshi，而是构建自有基建。

#### CME Group — 传统金融重量级

**关键数据：**
- 2025/12 上线事件合约
- 8 周内达到 **1 亿合约**
- 与 FanDuel 合作推出 "FanDuel Predicts"（全 50 州）
- 覆盖：S&P 500、油价、体育（在无合法体育博彩的州）

**战略意义：** 传统金融巨头入场，带来深度流动性和机构信誉。CME + FanDuel 合作是跨行业创新——将预测市场与体育娱乐结合。

#### Interactive Brokers — ForecastEx（最机构化定位）

- 自建 DCM+DCO
- **免佣金 + 持仓利息激励**（独一无二）
- 2026/1 聘请 Philip Tetlock（《超级预测》作者）进入董事会
- 聚焦经济和政治事件（更专业/机构受众）
- 计划扩展至 2026 中期选举

---

## 4. TIER 3: BNB Chain / CZ 生态

### 4.1 生态总览

BNB Chain 已成为预测市场第三极（仅次于 Polymarket/Polygon 和 Kalshi/中心化）：

| 指标 | 数据 |
|------|------|
| BNB Chain 预测市场累计交易量 | $20.91B+ |
| 主要平台 | Opinion Lab, predict.fun, Myriad 等 |

### 4.2 Opinion Lab（CZ 背书的核心平台）

| 维度 | 详情 |
|------|------|
| **上线** | Oct 2025 |
| **支持** | CZ 公开背书；YZi Labs（原 Binance Labs）种子轮 $5M（Mar 2025） |
| **链** | BNB Chain |
| **Token** | OPN |
| **月交易量** | $8.08B（Jan 2026） |
| **月活用户** | 101,954（Jan 2026） |
| **累计手续费** | $13M+ |
| **市场类别** | 体育、加密、政治、文化 |

**战略意义：** CZ 亲自推广；YZi Labs（Binance Labs 更名）直接投资。已产生实质性交易量和收入。代表 Binance 生态在预测市场的核心布局。

### 4.3 predict.fun

| 维度 | 详情 |
|------|------|
| **上线** | Dec 2025（CZ 于 Dec 5, 2025 介绍） |
| **链** | BNB Chain |
| **首周数据** | 12,000 用户，300K 投注，~$300K 交易量 |
| **特点** | AI 驱动；CZ "I am a fan" 公开支持 |

### 4.4 其他 BNB Chain 预测项目

| 平台 | 交易量 | 特点 |
|------|--------|------|
| **Myriad** | $100M+（3 个月 10x 增长） | BNB Chain 原生 |
| **Trust Wallet** | N/A | 集成 Polymarket 和 Kalshi 接口 |

### 4.5 CZ 对预测市场的立场

CZ 公开多次表达对预测市场的看好：
- 公开推广 Opinion Lab 和 predict.fun
- YZi Labs（Binance Labs）直接投资 Opinion Lab
- Trust Wallet 集成 Polymarket/Kalshi
- BNB Chain 生态主动吸引预测市场项目

---

## 5. TIER 4: 体育博彩/事件合约跨界

| 平台 | 状态 | 详情 |
|------|------|------|
| **FanDuel** | 已上线 "FanDuel Predicts" | 与 CME 合作；覆盖全 50 州；S&P 500、油价、体育合约 |
| **DraftKings** | 已上线 "DraftKings Predictions" | 2025 年底上线，覆盖 38 州；计划 2026 年投入 $400M |
| **Underdog** | Coalition 成员 | 体育/幻想平台；Coalition for Prediction Markets 创始成员 |
| **Sporttrade** | 运营中 | 5 州运营；已向 CFTC 提交 DCM 申请 |
| **Betfair Exchange** | 对标模型 | UK/Irish 市场 <£1B（从 2020 年 £1.5B 下降）；交易所模式类似预测市场 |

---

## 6. TIER 5: 基础设施与做市商

### 6.1 做市商

| 机构 | 角色 | 详情 |
|------|------|------|
| **Susquehanna (SIG)** | Kalshi Designated MM；Robinhood JV 合伙人 | 2024/4 首个机构 DMM 入驻 Kalshi；与 Robinhood 成立 JV 收购 MIAXdx；新交易所 Day-1 流动性提供者 |
| **Jump Trading** | Polymarket 战略 LP | 收购 Polymarket 少数股权（"equity-for-liquidity" 安排）；提供深度订单簿流动性 |
| **Wintermute** | 自建平台 OutcomeMarket | 2024/9 与 Chaos Labs 合作推出；首个自建预测平台的加密做市商 |
| **Citadel Securities** | 探索入场 | CEO Peng Zhao 参投 Kalshi（Jun 2025）；报道称探索自建或投资 |

### 6.2 预言机/基础设施

| 项目 | 角色 | 详情 |
|------|------|------|
| **UMA Protocol** | Polymarket 主要预言机 | Optimistic Oracle（提议→争议→投票）；适合主观/非价格市场 |
| **Chainlink** | Polymarket 补充预言机 | Data Streams（亚秒级延迟）+ Automation（自动结算）；适合价格市场 |
| **Gnosis** | Conditional Token Framework (CTF) | Polymarket 使用的 token 标准；Safe 多签钱包生态 |
| **Chaos Labs** | Wintermute 合作方 | 与 Wintermute 共建 OutcomeMarket |

---

## 7. 入场模式对比分析

### 7.1 两种主流入场路径

```
路径 A: 合作模式 (Partnership)
├── 优点: 快速上线（3-6个月），低资本投入，借用现有监管牌照
├── 缺点: 受限于合作方产品，利润分成，无自主定价权
├── 代表: Coinbase→Kalshi, Webull→Kalshi, 初期 Robinhood→Kalshi
└── 适用: 快速验证市场需求

路径 B: 自建/收购模式 (Build/Acquire)
├── 优点: 完全控制产品和定价，长期利润最大化，可做市
├── 缺点: 周期长（6-18个月），需获取 DCM 牌照，高资本投入
├── 代表: Robinhood→MIAXdx ($JV), Kraken→Small Exchange ($100M),
│         Gemini（新获 DCM）, CME（已有基建）, Interactive Brokers
└── 适用: 长期战略布局
```

### 7.2 Binance 可选路径分析

| 路径 | 描述 | 优先级 | 难度 |
|------|------|--------|------|
| **A1: 合作 Kalshi** | 类似 Coinbase/Webull 模式，快速上线 | 低（Kalshi 已饱和分发合作） | 低 |
| **A2: 合作 Polymarket** | 链上集成，Trust Wallet 已有基础 | 中 | 中 |
| **B1: BNB Chain 原生** | 利用 Opinion Lab/predict.fun 生态 | **高（已在进行）** | 中 |
| **B2: 收购 DCM** | 类似 Robinhood/Kraken 模式 | 低（Binance 美国监管历史复杂） | 高 |
| **C: Convert 做市商** | 聚合外部市场价格，Convert RFQ 报价 | **最高** | 中 |
| **D: OTC B2B 流动性** | 向外部平台提供流动性 | 高 | 低 |

---

## 8. 费率对比

| 平台 | 交易费 | 做市商费 | 提现费 | 特色 |
|------|--------|---------|--------|------|
| **Polymarket** | 0% | 0% | Gas only | 最低成本 |
| **Kalshi** | ~1% take rate | 优惠费率 | Free (ACH) | Cap $1.74/$100 |
| **Robinhood** | $0.01/合约 | N/A | Free | 低费透明 |
| **Interactive Brokers** | 0% | N/A | Free | 免佣 + 利息激励 |
| **Coinbase** | 含在价格中 | N/A | USDC settlement | 不透明 |
| **Webull** | 0%（交易所费另计） | N/A | Free | 零佣金 |
| **CME** | 标准衍生品费率 | 做市商折扣 | N/A | 机构级 |
| **PredictIt** | 10% 利润 + 5% 提现 | N/A | 5% | 最高费率 |
| **Opinion Lab** | 低 | N/A | Gas | BNB Chain 低 gas |

---

## 9. Coalition for Prediction Markets

**成立：** December 2025

**创始成员：**
1. Kalshi — 锚定平台
2. Coinbase — 加密交易所
3. Robinhood — 零售经纪
4. Crypto.com — 加密交易所
5. Underdog — 体育/幻想平台

**领导层：**
- CEO: 前国会议员 Sean Patrick Maloney
- 高级顾问: 前国会议员 Patrick McHenry

**2025 年各成员游说支出：**

| 成员 | 2025 游说支出 | 备注 |
|------|-------------|------|
| Crypto.com | ~$2,000,000 | 2025/5 开设华盛顿办公室 |
| Coinbase | ~$1,790,000 | 聚焦数字资产市场明确法案 |
| Robinhood | ~$510,000 | 资本市场、加密、经纪商监管 |
| Kalshi | ~$80,000 | 2026 初开设华盛顿办公室 |

**核心目标：**
- 推动 CFTC 独占联邦管辖权（vs 州级赌博分类）
- 反击传统博彩行业游说
- 2026/1 启动 "七位数倡议运动"

**Binance 缺席 Coalition** — 这是一个值得关注的战略缺口。

---

## 10. 关键竞争维度矩阵

| 维度 | Polymarket | Kalshi | Robinhood | Coinbase | CME | Binance (现状) |
|------|-----------|--------|-----------|----------|-----|---------------|
| **交易量** | $21.5B/yr | $23.8B/yr | 120亿合约/yr | 新上线 | 8周1亿合约 | 无产品 |
| **用户数** | 477K+ | 75K DAU | 数千万 | 数千万 | 机构为主 | 200M+ 注册 |
| **监管** | CFTC (新获) | CFTC DCM | DCM (via MIAXdx) | via Kalshi | 已有 | 复杂 |
| **技术** | 链上 CLOB | 中心化 | 中心化 | via Kalshi | 中心化 | 强（未应用） |
| **做市** | Jump Trading | SIG | SIG | N/A | 自有 | 可能性最大 |
| **费率** | 0% | ~1% | $0.01 | 含在价格 | 标准 | - |
| **全球覆盖** | 全球 | 仅美国 | 主要美国 | 主要美国 | 全球 | 全球 |
| **加密原生** | 是 | 否 | 部分 | 是 | 否 | 是 |
| **BNB 生态** | 无 | 无 | 无 | 无 | 无 | Opinion Lab, predict.fun |

---

## 11. 对 Binance Convert/OTC 的战略启示

### 11.1 Binance 的独特优势

1. **全球最大用户基数（200M+）**— 任何预测市场平台都无法匹敌的分发能力
2. **加密原生 + 全球覆盖**— 不受美国单一市场限制
3. **BNB Chain 生态已布局**— Opinion Lab ($8B+/月) 验证了需求
4. **Convert RFQ 模型**— 与零售预测市场完美匹配
5. **OTC 做市能力**— 可直接复用为预测市场做市商

### 11.2 Binance 的关键劣势

1. **美国市场准入受限**— 2023 年和解后监管敏感
2. **未加入 Coalition for Prediction Markets**— 缺乏政策影响力
3. **零产品发布**— 竞争对手已密集入场
4. **窗口期正在关闭**— 2026 H1 是最后的有利时间窗口

### 11.3 建议行动

| 优先级 | 行动 | 参考竞品 |
|--------|------|---------|
| **P0** | 通过 Convert 推出零售预测市场（做市商模式）| Coinbase Predictions 的 RFQ 化 |
| **P0** | OTC desk 在 Polymarket/Kalshi 部署做市策略 | Jump Trading, SIG 模式 |
| **P1** | 深化 BNB Chain 预测市场生态（Opinion Lab 集成） | CZ 已在推动 |
| **P1** | 评估非美国 DCM 等效牌照获取 | Dubai DFSA, Singapore MAS |
| **P2** | 评估是否加入 Coalition for Prediction Markets | Coinbase, Robinhood 已加入 |
| **P2** | 探索 Polymarket 做市（equity-for-liquidity 模式） | Jump Trading 模式 |

---

*本报告基于 2026 年 2 月 25 日的公开信息研究编制。市场数据可能快速变化，投资和产品决策前请验证原始数据源。*
