# PDX 合约集成方案：证伪赏金市场

> 结合智能合约 + 加密支付 + ClawHub 技能 + 340K 用户基础

---

## 核心设计：证伪赏金协议

```
不是"先做工具后上链"，而是从第一天就用合约驱动经济循环：

用户提出命题 + 质押 USDC
     ↓
OpenClaw 智能体自动证伪
     ↓
证据哈希上链 → 证伪者领取赏金
     ↓
命题存活率 = 可信度评级

为什么加密支付是关键：
  - 全球无门槛（不需要银行账户/Stripe/PayPal）
  - 微支付零摩擦（Base L2 单笔 <$0.01 gas）
  - 智能合约自动托管和清算（无需信任第三方）
  - OpenClaw 用户群天然是加密用户（已有钱包能力）
```

---

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    用户层（340K OpenClaw 用户）             │
│                                                         │
│  /pdx-submit "命题" --stake 5    提交命题 + 质押 5 USDC   │
│  /pdx-hunt                       浏览待证伪命题           │
│  /pdx-verify <id>                对命题执行证伪            │
│  /pdx-report <id>                查看证伪报告（付费）       │
│  /pdx-balance                    查看收益余额              │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              ClawHub 技能层（pdx-verify）                  │
│                                                         │
│  SKILL.md：证伪引擎指令                                    │
│  scripts/chain.py：合约交互脚本                            │
│  scripts/verify.py：证伪流水线                             │
│                                                         │
│  功能：                                                   │
│  1. 命题解析 → 提取可验证声明                              │
│  2. 多角度搜索反证                                        │
│  3. 证据评估和评分                                        │
│  4. 证据哈希计算 + 合约交互                                │
│  5. 结构化报告生成                                        │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              智能合约层（Base L2）                         │
│                                                         │
│  PDXProposition.sol                                     │
│    - createProposition(hash, metadata) payable          │
│    - getOpenPropositions() view                         │
│                                                         │
│  PDXFalsification.sol                                   │
│    - submitEvidence(propId, evidenceHash) → 领取赏金      │
│    - rateEvidence(propId, evidenceId, score) → 评审      │
│                                                         │
│  PDXReputation.sol                                      │
│    - 证伪者声誉积分（基于历史证伪质量）                     │
│    - 命题提交者声誉（命题质量历史）                         │
│                                                         │
│  支付代币：USDC（稳定币，无波动风险）                       │
│  网络：Base L2（Coinbase 生态，gas 极低）                  │
└─────────────────────────────────────────────────────────┘
```

---

## 智能合约设计

### 合约 1：PDXProposition（命题注册）

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract PDXProposition {
    IERC20 public usdc;

    enum Status { OPEN, FALSIFIED, SURVIVED, EXPIRED }

    struct Proposition {
        address creator;
        bytes32 contentHash;       // 命题内容的 keccak256
        string metadata;           // IPFS CID 或简短描述
        uint256 stake;             // 质押金额（USDC）
        uint256 bountyPool;        // 赏金池（= stake × 80%）
        uint256 protocolFee;       // 协议费（= stake × 5%）
        uint256 createdAt;
        uint256 expiresAt;         // 证伪窗口截止时间
        Status status;
        uint256 falsificationCount; // 被证伪次数
    }

    uint256 public propositionCount;
    mapping(uint256 => Proposition) public propositions;

    // 创建命题：质押 USDC
    function createProposition(
        bytes32 contentHash,
        string calldata metadata,
        uint256 stakeAmount,
        uint256 duration          // 证伪窗口时长（秒）
    ) external returns (uint256 propId);

    // 查看开放命题
    function getOpenPropositions()
        external view returns (uint256[] memory);

    // 命题到期未被有效证伪 → 创建者收回质押
    function claimSurvived(uint256 propId) external;
}
```

### 合约 2：PDXFalsification（证伪提交与奖励）

```solidity
contract PDXFalsification {
    struct Evidence {
        address falsifier;
        bytes32 evidenceHash;     // 证据内容的 keccak256
        string reportCID;         // 完整报告的 IPFS CID
        uint256 submittedAt;
        uint8 rating;             // 0-100 质量评分
        bool rewarded;
    }

    mapping(uint256 => Evidence[]) public evidences; // propId => evidences

    // 提交证伪证据
    function submitEvidence(
        uint256 propId,
        bytes32 evidenceHash,
        string calldata reportCID
    ) external returns (uint256 evidenceId);

    // 证据评审（由其他证伪者或协议验证者评分）
    function rateEvidence(
        uint256 propId,
        uint256 evidenceId,
        uint8 score               // 0-100
    ) external;

    // 领取赏金（证据评分 > 阈值即可领取）
    function claimReward(uint256 propId, uint256 evidenceId) external;

    // 查看命题的所有证伪证据
    function getEvidences(uint256 propId)
        external view returns (Evidence[] memory);
}
```

### 合约 3：PDXReputation（声誉系统）

```solidity
contract PDXReputation {
    struct Profile {
        uint256 totalFalsifications;   // 总证伪次数
        uint256 acceptedFalsifications; // 被接受的证伪次数
        uint256 totalEarned;           // 总收入（USDC）
        uint256 reputationScore;       // 声誉分 0-1000
    }

    mapping(address => Profile) public profiles;

    // 更新声誉（由 PDXFalsification 合约调用）
    function updateReputation(
        address user,
        bool accepted,
        uint256 earned
    ) external;

    // 查看声誉
    function getReputation(address user)
        external view returns (Profile memory);
}
```

---

## 经济模型

### 资金流转

```
命题创建者质押 100 USDC
     │
     ├─→ 80 USDC → 赏金池（给证伪者）
     │     │
     │     ├─→ 第一个有效证伪者：50 USDC（首发奖励）
     │     ├─→ 第二个增量证伪者：20 USDC
     │     └─→ 第三个增量证伪者：10 USDC
     │
     ├─→ 5 USDC → 协议金库（PDX 团队运营）
     │
     ├─→ 10 USDC → 评审奖励池（给质量评审者）
     │
     └─→ 5 USDC → 创建者退还（激励提出好命题）

如果命题存活（到期未被有效证伪）：
  创建者收回 80 USDC（赏金池原封退还）
  5 USDC 协议费不退
  15 USDC 评审费不退

为什么这样设计：
  - 创建者有激励提出真实可辩论的命题（低质量命题浪费质押）
  - 证伪者有激励找到高质量反证（越早+越独特 = 赚越多）
  - 评审者有激励公正评分（声誉系统惩罚恶意评审）
  - 协议有持续收入（每笔命题 5% 手续费）
```

### 最低质押门槛

```
命题类型          最低质押    证伪窗口    赏金池
─────────────────────────────────────────────
快速验证          1 USDC     24 小时     0.80 USDC
标准验证          5 USDC     72 小时     4.00 USDC
深度验证          25 USDC    7 天        20.00 USDC
重大命题          100+ USDC  14 天       80.00+ USDC

最低 1 USDC 门槛 → 让任何人都能参与
Base L2 gas 费 <$0.01 → 不会被手续费吃掉
```

### 交易量预估

```
假设 Day 90（3个月后）：
  日新增命题：100 个
  平均质押：10 USDC
  每个命题平均 3 次证伪提交
  每个证伪报告平均 5 次查看

日链上交易：
  100（创建命题）
  + 300（提交证伪）
  + 300（评审评分）
  + 500（查看报告）
  + 100（领取赏金）
  = 1,300 笔/天

日协议收入：
  100 × 10 USDC × 5% = 50 USDC/天 = 1,500 USDC/月

年化：
  如果增长到 1,000 命题/天 → 15,000 USDC/月 = $180K/年
```

---

## ClawHub 技能设计

### 目录结构

```
~/.openclaw/skills/pdx-verify/
├── SKILL.md                    # 核心指令
├── scripts/
│   ├── chain.py                # 合约交互（ethers.py / web3.py）
│   │   ├── create_proposition()
│   │   ├── submit_evidence()
│   │   ├── claim_reward()
│   │   └── get_open_propositions()
│   ├── verify.py               # 证伪引擎
│   │   ├── parse_proposition()
│   │   ├── multi_angle_search()
│   │   ├── evaluate_evidence()
│   │   └── generate_report()
│   └── ipfs.py                 # IPFS 上传（证伪报告存储）
└── references/
    ├── credibility_sources.md  # 来源可信度评级表
    └── contract_abi.json       # 合约 ABI
```

### SKILL.md 核心指令

```yaml
---
name: pdx_verify
description: 证伪赏金市场 - 提交命题质押USDC，证伪赚取赏金
user-invocable: true
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env:
        - PDX_WALLET_KEY     # 用户钱包私钥（可选，用于链上交互）
---

# PDX 证伪赏金市场

## 命令

### /pdx-submit <命题> --stake <金额>
提交一个命题到链上，质押 USDC 作为赏金。
1. 解析命题是否可证伪（具体、有时间限定、可验证）
2. 调用 scripts/chain.py 创建链上命题
3. 确认质押成功后显示命题 ID

### /pdx-hunt
浏览当前开放的待证伪命题列表。
1. 调用 scripts/chain.py 获取开放命题
2. 按赏金金额排序显示
3. 显示每个命题的剩余时间和当前证伪次数

### /pdx-verify <命题ID>
对指定命题执行结构化证伪。
1. 从链上获取命题内容
2. 执行多角度搜索（英文/中文/行业源）
3. 评估每条证据的可信度和力度
4. 生成结构化证伪报告
5. 上传报告到 IPFS
6. 提交证据哈希到链上
7. 如果证据质量达标 → 自动领取赏金

### /pdx-report <命题ID>
查看命题的证伪报告（链上数据 + IPFS 报告）。

### /pdx-balance
查看当前钱包的 PDX 证伪收益。

## 证伪策略
[... 同之前的多角度搜索策略 ...]

## 报告格式
[... 同之前的 A/B/C/D/F 评级 ...]
```

---

## 用户体验流程

### 场景 1：提交命题（信息消费者）

```
用户：/pdx-submit "台积电3nm良率已达80%" --stake 10

AI 智能体：
  ✅ 命题可证伪性检查通过
  ✅ 钱包余额检查：42.5 USDC
  ⏳ 正在提交到 Base 链上...
  ✅ 命题已创建！

  ┌─────────────────────────────────────┐
  │ 命题 #1847                          │
  │ "台积电3nm良率已达80%"               │
  │ 质押：10 USDC                       │
  │ 赏金池：8 USDC                      │
  │ 证伪窗口：72小时（至 4月3日 14:00）   │
  │ 状态：OPEN                          │
  │ 查看：base.blockscout.com/tx/0x...  │
  └─────────────────────────────────────┘

  💡 提示：如果 72 小时内没有有效证伪，
     你将收回 8 USDC 赏金池 + 获得"高置信度"标签。
```

### 场景 2：证伪赚赏金（信息生产者）

```
用户：/pdx-hunt

AI 智能体：
  ┌─────────────────────────────────────────────┐
  │ 📋 开放命题列表（按赏金排序）                  │
  │                                             │
  │ #1852  赏金 80 USDC  ⏰ 6天剩余              │
  │ "2026年美联储将降息至少3次"                    │
  │ 已有 2 条证伪 | 深度验证                      │
  │                                             │
  │ #1849  赏金 20 USDC  ⏰ 5天剩余              │
  │ "苹果正在开发折叠屏iPhone原型机"               │
  │ 已有 0 条证伪 | 标准验证                      │
  │                                             │
  │ #1847  赏金 8 USDC   ⏰ 2天剩余              │
  │ "台积电3nm良率已达80%"                        │
  │ 已有 1 条证伪 | 标准验证                      │
  └─────────────────────────────────────────────┘

用户：/pdx-verify 1849

AI 智能体：
  ⏳ 正在证伪命题 #1849...
  🔍 搜索英文新闻源... 找到 12 条相关结果
  🔍 搜索中文新闻源... 找到 8 条相关结果
  🔍 搜索行业报告... 找到 3 条相关结果
  🔍 搜索社交媒体... 找到 5 条相关结果
  📊 评估证据质量...

  ┌─────────────────────────────────────────────┐
  │ 证伪报告 #1849                               │
  │ "苹果正在开发折叠屏iPhone原型机"               │
  │                                             │
  │ 评级：B（高置信度 — 发现强力反证）             │
  │                                             │
  │ 🔴 反证 1（强）：                             │
  │   Ming-Chi Kuo 最新报告称折叠屏 iPhone        │
  │   已从 2026 路线图中移除，转为 2027+           │
  │   来源可信度：9/10                            │
  │                                             │
  │ 🔴 反证 2（强）：                             │
  │   苹果供应链消息称折叠屏面板订单已取消          │
  │   来源：DigiTimes 2026/3/15                  │
  │   来源可信度：7/10                            │
  │                                             │
  │ 🟢 支持证据 1：                               │
  │   2025 年苹果折叠屏专利申请（但专利≠产品）      │
  │                                             │
  │ 结论：该命题很可能不准确                       │
  └─────────────────────────────────────────────┘

  ⏳ 上传报告到 IPFS... ✅ CID: Qm...abc
  ⏳ 提交证据到链上... ✅ tx: 0x...def
  💰 首个证伪者奖励：12.5 USDC 已到账！

  查看链上记录：base.blockscout.com/tx/0x...
```

---

## 三步走路线图（修订版）

### Step 1：MVP — 技能 + 合约（4-6周，$2K）

```
Week 1-2：ClawHub 技能开发
  - SKILL.md 证伪引擎指令
  - scripts/verify.py 证伪流水线
  - 本地测试 20 个命题

Week 3-4：智能合约开发 + 部署
  - PDXProposition.sol + PDXFalsification.sol
  - 部署到 Base Sepolia 测试网
  - scripts/chain.py 合约交互脚本
  - IPFS 报告存储

Week 5-6：集成测试 + 发布
  - 端到端测试（提交→证伪→领赏金）
  - 部署到 Base 主网
  - 提交 ClawHub
  - 准备 10 个种子命题（PDX 团队质押）

成本明细：
  合约审计（基础）：$500-1,000（用 Slither 自动审计 + 社区审核）
  Base 主网部署 gas：<$1
  IPFS pinning（Pinata 免费层）：$0
  测试 API 费用：$200
  种子命题质押：$500（会回收）
  ─────────
  总计：~$1,500-$2,000

成功标准：
  ✅ 500+ 技能安装量
  ✅ 50+ 命题被创建
  ✅ 有人通过证伪赚到 USDC
  ❌ 失败 = < 50 安装 → 停止
```

### Step 2：飞轮加速（8-12周，$5K-$10K）

```
前提：Step 1 有 50+ 活跃命题

新增功能：
  1. PDXReputation 合约部署
     - 证伪者声誉积分
     - 声誉越高 → 优先领取高额赏金

  2. 命题分类和领域路由
     - 科技/金融/地缘/加密 四大领域
     - 领域专家 bot 配置（利用 OpenClaw 的领域技能）

  3. 证伪报告 NFT 化（可选）
     - 高质量证伪报告铸造为 NFT
     - 报告创作者持续收取查看费

  4. Web 仪表板
     - 浏览命题和证伪报告
     - 排行榜（顶级证伪者）
     - 命题可信度实时追踪

  5. 评审机制
     - 质押用户可以对证伪报告投票
     - 评审者赚取评审奖励

交易量预期：
  日命题 100+ → 日链上交易 1,300+ 笔
  协议月收入 $1,500+
```

### Step 3：完整证伪市场（16-24周，$20K-$50K）

```
前提：Step 2 协议月收入 > $5K

新增功能：
  1. $PDX 治理代币（可选）
     - 协议治理投票
     - 质押 $PDX 获得协议费分红
     - 不做 utility token 的投机叙事

  2. 预测市场叠加层
     - 在存活率高的命题上开放下注
     - 赔率基于证伪存活率
     - 所有证据链公开透明

  3. B2B API
     - 对冲基金/媒体/AI 公司订阅证伪数据
     - 按 API 调用量收费

  4. 多链部署
     - Base + Arbitrum + 其他 L2
     - 跨链命题同步
```

---

## 为什么这是最优方案

### 对比矩阵

```
维度              纯工具（旧方案）    合约集成（新方案）
───────────────────────────────────────────────
经济激励          无                 质押+赏金（USDC）
用户粘性          低（用完就走）     高（有钱赚）
网络效应          弱                 强（更多质押=更多证伪者）
分发渠道          ClawHub 340K      ClawHub 340K + 加密社区
收入模式          无                 协议费 5%/笔
交易量            0                  日均 1,300+ 笔
可验证性          报告在本地         报告哈希+时间戳上链
抗审查            无                 完全去中心化
```

### 五维度可行性

```
1. 技术可行性：⭐⭐⭐⭐
   - OpenClaw 已有 Base 网络插件和钱包能力
   - 合约逻辑简单（质押/领取/评审）
   - Base L2 部署成本极低
   - 需要多 2 周开发合约（vs 纯技能方案）

2. 市场可行性：⭐⭐⭐⭐⭐
   - 340K OpenClaw 用户 + 加密社区双渠道
   - "证伪赚钱"比"免费工具"更有吸引力
   - 加密用户对赏金/质押模型非常熟悉

3. 经济可行性：⭐⭐⭐⭐
   - 总成本 ~$2K（vs 旧方案 $200）
   - 但有明确收入模型（协议费 5%）
   - 种子质押可回收

4. 竞争可行性：⭐⭐⭐⭐⭐
   - 全球无"链上证伪赏金"产品
   - UMA 做投票验证，不做 AI 证伪
   - Supra 做数据验证，不做命题证伪
   - Polymarket 做下注，不做证据链

5. 加密支付优势：⭐⭐⭐⭐⭐
   - 全球无门槛（任何有钱包的人都能参与）
   - Base L2 gas <$0.01（微支付可行）
   - 智能合约自动托管（无需信任平台）
   - USDC 稳定币（无汇率波动风险）
```

---

## 风险和缓解

```
风险 1：合约安全漏洞
  缓解：
  - 合约逻辑极简（存/取/评分，不做复杂 DeFi）
  - 用 OpenZeppelin 标准库
  - Slither + Mythril 自动审计
  - 先在测试网跑 2 周
  - 初期限制单笔质押上限（100 USDC）
  成本：$500-1,000（vs 正规审计 $10K+）

风险 2：证伪质量作弊（提交垃圾证据领赏金）
  缓解：
  - 证据需要评审投票达标才能领取赏金
  - 声誉系统惩罚低质量提交（降低优先级）
  - 初期由 PDX 团队做评审（Step 2 开放社区评审）

风险 3：命题质量低（提交无法证伪的命题骗赏金）
  缓解：
  - 命题创建需质押 → 低质量命题 = 浪费钱
  - 命题可证伪性检查（AI 自动筛选）
  - 社区举报机制

风险 4：监管风险
  缓解：
  - 不是赌博/预测市场（质押+证伪 ≠ 下注）
  - 使用稳定币 USDC（不发新代币）
  - 本质是"信息验证服务的付费模式"
  - Step 3 才考虑预测市场叠加（可选不做）

风险 5：OpenClaw 用户不愿连接钱包
  缓解：
  - 免费模式并行存在（/pdx-verify 不需要钱包）
  - 只有 /pdx-submit 和 /pdx-hunt 需要钱包
  - 很多 OpenClaw 用户已经有加密钱包（调研已确认）
```

---

## 与原始目标的对照

```
原始目标                           新方案                      状态
─────────────────────────────────────────────────────────────────
ETH L2 智能合约做 truth source    ✅ Base L2 合约从 Day 1       完全满足
加密货币支付便利性                 ✅ USDC 质押/赏金/微支付      完全满足
利用 Clawbot 广大用户基础         ✅ ClawHub 技能 340K 用户     完全满足
带动交易                          ✅ 日均 1,300+ 链上交易       完全满足
OpenClaw 算力参与                 ✅ 证伪 = 算力贡献            完全满足
预测市场理念                      ⚠️ Step 3 可选叠加           保留路径
```

---

## 一句话总结

```
在 ClawHub 做一个证伪赏金技能 + 在 Base L2 部署质押合约。
$2K，6周。340K 用户池 + 全球加密用户。
用户质押 USDC 提命题，AI 证伪赚赏金，协议抽 5%。
验证成功再加预测市场，失败了也就损失两千块。
```
