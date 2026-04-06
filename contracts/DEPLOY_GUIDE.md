# PDX 合约上链指南 (零基础版)

> 目标：把 PDX 预测市场合约部署到 Base Sepolia 测试网上，任何人可通过浏览器交互。
> 全程不需要花真钱 — 使用测试网 + 测试代币。

---

## 概念速查

| 术语 | 一句话解释 |
|------|-----------|
| **钱包** | 你在区块链上的"账号"，由一对密钥(公钥/私钥)组成 |
| **私钥** | 控制钱包的密码，绝对不能泄露给任何人 |
| **ETH** | 以太坊原生代币，用来支付"手续费"(gas) |
| **Base Sepolia** | Base 链的测试网，和正式网一模一样但用的是假钱 |
| **Gas** | 每次操作区块链都要付的手续费，测试网上免费领 |
| **合约** | 运行在区块链上的程序，一旦部署不可修改 |
| **ABI** | 合约的"接口文档"，告诉前端怎么调用合约 |

---

## Step 1: 安装 MetaMask 钱包

1. 打开 Chrome 浏览器
2. 访问 https://metamask.io/download/
3. 点击 "Add to Chrome" 安装插件
4. 按提示创建新钱包：
   - 设置密码
   - **抄写助记词**（12 个英文单词）→ 存在安全的地方
5. 安装完成后，右上角会出现 🦊 狐狸图标

---

## Step 2: 添加 Base Sepolia 测试网

MetaMask 默认只有以太坊主网，需要手动添加 Base 测试网：

1. 打开 MetaMask → 点击左上角网络选择器（显示 "Ethereum Mainnet"）
2. 点击 "Add network" → "Add a network manually"
3. 填入以下信息：

```
Network name:        Base Sepolia
RPC URL:             https://sepolia.base.org
Chain ID:            84532
Currency symbol:     ETH
Block Explorer URL:  https://sepolia.basescan.org
```

4. 点击 "Save"，然后切换到 "Base Sepolia" 网络

---

## Step 3: 获取测试 ETH (用来付 gas)

部署合约需要少量 ETH 做手续费（测试网免费领）：

1. 复制你的钱包地址：打开 MetaMask → 点击地址复制
   - 地址格式：`0x1234...abcd`

2. 打开水龙头领测试 ETH（以下任选一个）：
   - **推荐**: https://www.alchemy.com/faucets/base-sepolia
     - 需要注册 Alchemy 账号（免费）
     - 粘贴钱包地址 → 点击 "Send Me ETH"
   - 备选: https://faucet.quicknode.com/base/sepolia

3. 等待 10-30 秒，MetaMask 余额会显示 ETH（通常 0.05-0.1 ETH，足够部署）

---

## Step 4: 获取 Alchemy RPC URL

合约部署需要一个 RPC 节点来和区块链通信：

1. 访问 https://www.alchemy.com/ → 注册免费账号
2. 登录后 → Dashboard → "Create new app"
3. 设置：
   - Name: `PDX`
   - Chain: `Base`
   - Network: `Base Sepolia`
4. 创建后 → 点击 "API Key" → 复制 HTTPS URL
   - 格式：`https://base-sepolia.g.alchemy.com/v2/你的KEY`

---

## Step 5: 导出私钥

> ⚠️ 私钥 = 钱包的完全控制权。只在测试网使用，永远不要把含有真钱的钱包私钥放在文件里。

1. 打开 MetaMask → 点击三个点 → "Account details"
2. 点击 "Show private key" → 输入密码
3. 复制私钥（格式：`0x` 开头的 64 位十六进制字符串）

---

## Step 6: 配置环境变量

在 `contracts/` 目录下：

```bash
cd /Users/user/Desktop/vault/03-Projects/NUS/FT5004/pdx/contracts

# 复制模板
cp .env.example .env
```

编辑 `.env` 文件，填入你的信息：

```bash
PRIVATE_KEY=0x你的私钥
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/你的KEY
```

---

## Step 7: 部署合约 🚀

```bash
cd /Users/user/Desktop/vault/03-Projects/NUS/FT5004/pdx/contracts

# 加载环境变量
source .env

# 部署到 Base Sepolia
forge script script/Deploy.s.sol \
  --rpc-url $BASE_SEPOLIA_RPC_URL \
  --broadcast \
  --verify
```

### 成功后你会看到：

```
=== Deployment Summary ===
MockUSDC:    0x1111...1111
PDXMarket:   0x2222...2222
PDXOracle:   0x3333...3333
========================
```

**把这三个地址复制下来！** 后续步骤需要用到。

### 如果报错？

| 错误 | 原因 | 解决 |
|------|------|------|
| `insufficient funds` | ETH 不够付 gas | 回 Step 3 多领一些 |
| `could not connect` | RPC URL 错误 | 检查 .env 中的 URL |
| `invalid private key` | 私钥格式错 | 确保以 `0x` 开头，共 66 字符 |

---

## Step 8: 创建示例市场

部署成功后，更新 `.env` 添加合约地址：

```bash
MOCK_USDC=0x上面输出的MockUSDC地址
PDX_MARKET=0x上面输出的PDXMarket地址
PDX_ORACLE=0x上面输出的PDXOracle地址
```

然后创建一个示例市场：

```bash
source .env

forge script script/CreateMarket.s.sol \
  --rpc-url $BASE_SEPOLIA_RPC_URL \
  --broadcast
```

成功后会输出 Market ID（通常是 0）。

---

## Step 9: 验证合约 (在浏览器上查看)

1. 打开 https://sepolia.basescan.org
2. 搜索框粘贴 PDXMarket 地址 → 回车
3. 你会看到合约页面，点击 "Contract" → "Read Contract"
4. 可以调用 `getPriceYes(0)` 查看当前 YES 价格（应该返回 500000 = 50%）

如果 Step 7 的 `--verify` 成功了，你还会看到 "Read as Proxy" 和完整源码。

---

## Step 10: 在浏览器里交互 (手动测试)

### 10a. Mint 测试 USDC

1. BaseScan 搜索 MockUSDC 地址
2. "Contract" → "Write Contract" → "Connect to Web3"（连接 MetaMask）
3. 找到 `mint` 函数：
   - `to`: 粘贴你的钱包地址
   - `amount`: `100000000000` (= 100,000 USDC，因为 6 位小数)
4. 点 "Write" → MetaMask 确认交易

### 10b. Approve USDC 给 Market

1. 还是在 MockUSDC 的 "Write Contract"
2. 找到 `approve` 函数：
   - `spender`: 粘贴 PDXMarket 地址
   - `amount`: `115792089237316195423570985008687907853269984665640564039457584007913129639935`
     （这是 uint256 最大值，意思是"无限授权"）
3. 点 "Write" → 确认

### 10c. 买 YES Token

1. BaseScan 搜索 PDXMarket 地址
2. "Write Contract" → 连接 MetaMask
3. 找到 `buyYes` 函数：
   - `marketId`: `0`
   - `usdcAmount`: `1000000000` (= 1,000 USDC)
4. 点 "Write" → 确认
5. 去 "Read Contract" → `getPriceYes(0)` → 价格应该涨了！

---

## 文件清单

部署完成后，你的项目结构：

```
contracts/
├── foundry.toml          # Foundry 配置
├── .env                  # 你的私钥和 RPC (不要提交到 git!)
├── .env.example          # 配置模板
├── DEPLOY_GUIDE.md       # 本文档
├── src/
│   ├── MockUSDC.sol      # 测试 USDC 代币
│   ├── OutcomeToken.sol  # YES/NO 代币
│   ├── PDXMarket.sol     # 核心 AMM 预测市场
│   └── PDXOracle.sol     # 结算预言机
├── test/
│   └── PDXMarket.t.sol   # 20 个测试 (全部通过 ✅)
├── script/
│   ├── Deploy.s.sol      # 一键部署脚本
│   └── CreateMarket.s.sol # 创建示例市场
└── lib/                  # 依赖 (forge-std, OpenZeppelin)
```

---

## 常见问题

**Q: 部署要花真钱吗？**
A: 不要。Base Sepolia 是测试网，ETH 是免费领的，USDC 是我们自己的 MockUSDC。

**Q: 私钥放在 .env 安全吗？**
A: 测试网没问题。但如果这个钱包有真钱，绝对不要这样做。建议专门创建一个测试用的新钱包。

**Q: 合约部署后能修改吗？**
A: 不能。区块链上的合约是不可变的。如果有 bug，只能部署新合约。

**Q: 怎么让别人也能用？**
A: 把合约地址发给他们。他们在 MetaMask 切换到 Base Sepolia，用 BaseScan 就能交互。或者等前端做好直接访问网页。

**Q: gas 费用大概多少？**
A: 测试网不要钱。Base 正式网上大约 $0.01-$0.10 每次交易。
