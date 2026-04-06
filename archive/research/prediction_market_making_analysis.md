# Prediction Market Making (做市商) - Comprehensive Technical Analysis
## How a Crypto Exchange Like Binance Could Act as a Market Maker in Prediction Markets

**Date:** 2026-02-24
**Classification:** Internal Research Document

---

## Table of Contents

1. [Market Overview & Scale](#1-market-overview--scale)
2. [Prediction Market Making Mechanics](#2-prediction-market-making-mechanics)
3. [Market Making Strategies in Prediction Markets](#3-market-making-strategies-in-prediction-markets)
4. [Technical Infrastructure Requirements](#4-technical-infrastructure-requirements)
5. [Existing Binance Infrastructure Mapping](#5-existing-binance-infrastructure-mapping)
6. [Competitive Landscape](#6-competitive-landscape)
7. [Market Opportunities & Business Models](#7-market-opportunities--business-models)
8. [Regulatory Considerations](#8-regulatory-considerations)
9. [Strategic Recommendations for Binance](#9-strategic-recommendations-for-binance)

---

## 1. Market Overview & Scale

### 1.1 Market Size (2025 Data)

The prediction market sector experienced explosive growth in 2025:

| Metric | Value |
|--------|-------|
| **Global prediction market total trading volume (2025)** | ~$44 billion |
| **Polymarket trading volume (2025)** | $21.5 billion |
| **Kalshi trading volume (2025)** | $24 billion |
| **Combined Polymarket + Kalshi share** | ~99% of global market |
| **Year-over-year growth** | ~400% (from ~$9B in 2024) |
| **Global user base (2025)** | ~15 million |
| **VC funding into prediction markets (2025)** | $3.7 billion (35x increase YoY) |
| **Kalshi fee revenue (2025)** | $263.5 million |
| **Kalshi sports markets % of revenue** | 89% ($234.6M) |
| **Polymarket valuation (Oct 2025)** | $9 billion (ICE invested $2B) |
| **Kalshi valuation (2025)** | $11 billion |
| **Projected revenue by 2030** | $10 billion |
| **Long-term TAM estimate** | $1.3 trillion in total volume |

### 1.2 Key Growth Drivers
- Sports event contracts (87% of Kalshi volume)
- Integration with mainstream finance apps (Robinhood, Coinbase)
- Institutional market maker participation (Jump Trading, Susquehanna)
- Regulatory clarity trending toward federal CFTC oversight
- ICE (parent of NYSE) investing $2 billion in Polymarket

---

## 2. Prediction Market Making Mechanics

### 2.1 How Prediction Market Shares Work

Prediction market shares are **binary outcome tokens** priced between $0.00 and $1.00. Each share represents a claim on one side of a binary event (YES/NO). At settlement:
- Winning shares pay out **$1.00**
- Losing shares pay out **$0.00**
- The share price at any time reflects the market's implied probability of the event occurring

**Example:** A "Will BTC exceed $100K by Dec 2026?" YES share trading at $0.65 implies a 65% probability.

**Key Properties:**
- Complementary pairs: YES price + NO price = $1.00 (minus spread)
- Tick size: Typically $0.01 (1 cent increments)
- Shares can be created by depositing $1.00 collateral, receiving 1 YES + 1 NO share
- Shares can be redeemed: returning 1 YES + 1 NO share recovers $1.00 collateral

### 2.2 Order Book (CLOB) Model

**Used by:** Polymarket, Kalshi

Both major prediction market platforms use a **Central Limit Order Book (CLOB)** model, not AMMs, for their primary trading:

**Polymarket's CLOB Architecture:**
- Runs a hybrid on-chain/off-chain CLOB system
- Order matching occurs off-chain for performance (sub-second)
- Settlement and custody occur on-chain (Polygon blockchain)
- Uses the **Conditional Token Framework (CTF)** from Gnosis for token standards
- Orders specify: `tokenID`, `price` (0.00-1.00), `size` (share quantity), `side` (BUY/SELL)
- Tick size: $0.01
- Supports `negRisk` parameter for negative-risk market types
- API clients available: `@polymarket/clob-client` (TypeScript), `py_clob_client` (Python)

**Kalshi's CLOB Architecture:**
- Fully centralized, CFTC-regulated exchange
- Traditional exchange-grade matching engine
- Operates as a Designated Contract Market (DCM)
- Contracts denominated in USD (not crypto)
- Central counterparty clearing

**Why CLOB over AMM for prediction markets:**
1. Better price discovery for sophisticated markets
2. Enables professional market makers to quote two-sided markets
3. More capital efficient (no locked liquidity pools)
4. Supports limit orders, market orders, and complex order types
5. Allows for tighter spreads with professional liquidity provision

### 2.3 Automated Market Maker (AMM) Models

While CLOBs dominate the largest platforms, AMMs remain important for bootstrapping liquidity in new/low-volume markets:

#### 2.3.1 LMSR (Logarithmic Market Scoring Rule)

**Inventor:** Robin Hanson
**Originally used by:** Augur, Gnosis (early versions)

**Mechanism:**
- Functions as a central counterparty, always ready to buy/sell shares
- Uses a **cost function** based on logarithmic scoring to determine prices
- Price of outcome i: `p_i = e^(q_i/b) / SUM(e^(q_j/b))` where q_i = shares outstanding, b = liquidity parameter

**Key Parameter - Liquidity (b):**
- Set by market creator
- Lower b = more price-sensitive (prices move more per trade)
- Higher b = deeper market (more resistant to price changes)
- Maximum loss for market maker = `b * ln(n)` where n = number of outcomes

**Advantages:**
- **Bounded loss** for the market maker (predictable maximum cost)
- Guaranteed price coherence (all outcome probabilities sum to 100%)
- Works well for bootstrapping new markets with thin liquidity
- Interpretable prices as probabilities

**Disadvantages:**
- Subsidized model (market operator absorbs expected losses)
- Improperly set `b` parameter causes too much or too little volatility
- Less capital efficient than CLOB for high-volume markets
- Single liquidity parameter may not adapt well to changing conditions

#### 2.3.2 CPMM (Constant Product Market Maker)

**Popularized by:** Uniswap
**Used by:** Some DeFi prediction markets

**Mechanism:**
- Liquidity pool contains reserves of YES and NO tokens
- Trading governed by: `x * y = k` (constant product formula)
- Price determined by ratio of tokens in pool
- Liquidity providers (LPs) deposit paired tokens and earn fees

**In Prediction Market Context:**
- Pool holds YES tokens (quantity x) and NO tokens (quantity y)
- Buying YES tokens increases NO token quantity, decreases YES quantity
- Price of YES = y / (x + y)

**Advantages:**
- No subsidized market maker needed
- Permissionless liquidity provision
- Simple, battle-tested mechanism from DeFi
- Works on-chain without off-chain infrastructure

**Disadvantages:**
- **Severe impermanent loss** in prediction markets: since one outcome token goes to $1.00 and the other to $0.00, LP losses become *permanent* and substantial
- Prices may not sum to exactly 100% in multi-outcome markets (requires arbitrageurs)
- Less capital efficient than CLOB
- Higher slippage for large trades

#### 2.3.3 Comparison Matrix

| Feature | CLOB | LMSR | CPMM |
|---------|------|------|------|
| **Used by** | Polymarket, Kalshi | Augur (historical) | DeFi prediction platforms |
| **Liquidity source** | Professional market makers | Subsidized by operator | Decentralized LPs |
| **Capital efficiency** | Highest | Medium | Lowest |
| **Price coherence** | Depends on arbitrage | Guaranteed | Requires arbitrage |
| **Best for** | High-volume markets | New/niche markets | Permissionless on-chain |
| **Market maker risk** | Managed by MM | Bounded loss | Impermanent/permanent loss |
| **Spread control** | Full MM control | Determined by `b` | Determined by pool depth |
| **Latency** | Lowest (off-chain matching) | Medium | On-chain speed |

---

## 3. Market Making Strategies in Prediction Markets

### 3.1 How Market Makers Profit

Market makers in prediction markets earn returns through several mechanisms:

**A. Bid-Ask Spread Capture**
- Quote YES shares at $0.64 bid / $0.66 ask (2-cent spread)
- Simultaneously quote NO shares at $0.34 bid / $0.36 ask
- Each round-trip trade captures the spread
- Spread wider for illiquid/volatile markets, tighter for liquid ones
- Typical spreads: 1-5 cents for liquid markets, 5-15 cents for illiquid

**B. Rebates & Fee Advantages**
- Designated market makers receive reduced fees or rebates
- Kalshi offers reduced fees and enhanced position limits to designated MMs
- Polymarket: maker fees are typically 0%, taker fees apply

**C. Arbitrage**
- Cross-platform arbitrage (Polymarket YES at $0.60, Kalshi YES at $0.63)
- Intra-market arbitrage (YES + NO prices not summing to $1.00)
- Cross-asset arbitrage (prediction market vs. derivatives/options)

**D. Information Edge**
- Superior modeling of event probabilities using proprietary data
- Faster incorporation of news/data into pricing
- Quantitative models: polling aggregation, sentiment analysis, on-chain data

### 3.2 Key Differences from Traditional Crypto Market Making

| Dimension | Traditional Crypto MM | Prediction Market MM |
|-----------|----------------------|---------------------|
| **Asset lifetime** | Perpetual | Finite (expires at event) |
| **Terminal value** | Unknown | Binary ($0 or $1) |
| **Inventory risk** | Price risk (continuous) | Event risk (binary jump) |
| **Hedging** | Delta hedge with perps/options | Limited hedging options |
| **Information** | Price/flow data | Polls, news, domain expertise |
| **Correlation** | Correlated across crypto assets | Often uncorrelated (idiosyncratic events) |
| **Liquidity** | Deep for majors | Thin for most markets |
| **Settlement** | Continuous | Event-driven, single point |
| **Market hours** | 24/7 | 24/7 but activity event-driven |

### 3.3 Risk Management

#### 3.3.1 Inventory Risk
- **Problem:** Accumulating a large YES or NO position before event resolution
- **Mitigation:**
  - Skew quotes based on inventory (widen bid on overloaded side)
  - Set maximum inventory limits per market
  - Use portfolio-level offsetting across correlated markets
  - Dynamic position sizing based on time-to-event

#### 3.3.2 Event Risk (Jump Risk)
- **Problem:** Binary outcome creates sudden, complete loss on losing side
- **Characteristics unique to prediction markets:**
  - No gradual price movement -- information arrives in bursts
  - "Surprise" outcomes can cause 100% loss on inventory
  - Unlike spot trading, there is no "average down" strategy near settlement
- **Mitigation:**
  - Reduce position sizes near event resolution
  - Widen spreads during high-uncertainty periods
  - Portfolio diversification across many uncorrelated events
  - Hedge with correlated financial instruments where possible (e.g., election outcome vs. equity sectors)

#### 3.3.3 Information Asymmetry
- **Problem:** Informed traders (insiders, domain experts) trade against the market maker
- **Mitigation:**
  - Monitor for adverse selection patterns
  - Widen spreads for markets susceptible to insider information
  - Use trade-size limits to prevent large informed orders
  - Analyze order flow toxicity metrics (VPIN, Kyle's lambda)

#### 3.3.4 Liquidity Risk
- **Problem:** Low-volume markets make it hard to exit positions
- **Mitigation:**
  - Focus market making on high-volume, time-bound events
  - Use minting/redemption to manage inventory (create YES+NO pairs from collateral, or redeem pairs for collateral)
  - Maintain collateral reserves for redemption operations

#### 3.3.5 Long-Dated Position Risk
- **Problem:** Capital tied up for months in long-dated markets
- **Mitigation:**
  - Capital allocation models that account for duration
  - Prioritize short-dated, high-turnover events (sports, weekly economic data)
  - Price in time value / cost of capital into spread

### 3.4 Spread Management Framework

```
Optimal Spread = Base Spread
                 + Inventory Adjustment
                 + Volatility Adjustment
                 + Information Asymmetry Premium
                 + Time-to-Event Adjustment
                 + Cost-of-Capital Component
```

**Base Spread:** Minimum profitable spread (covers fees + operational costs)
**Inventory Adjustment:** Wider on overloaded side, tighter on needed side
**Volatility Adjustment:** Wider when new information expected (debate, earnings, game day)
**Information Asymmetry Premium:** Wider for markets prone to insider knowledge
**Time-to-Event Adjustment:** Tighter far from event (more time to rebalance), wider near event
**Cost-of-Capital:** For long-dated markets, embed financing cost into spread

---

## 4. Technical Infrastructure Requirements

### 4.1 Core Systems for Prediction Market Making

#### 4.1.1 Pricing Engine

A prediction market pricing engine differs from traditional crypto pricing engines:

**Inputs:**
- Real-world data feeds (polling, sports odds, economic indicators)
- On-chain data (current market prices, order book depth, trade flow)
- Sentiment data (social media, news NLP)
- Historical event data for calibration
- Competitor pricing (cross-platform arbitrage signals)

**Models:**
- Bayesian probability models for event outcomes
- Ensemble models combining multiple data sources
- Time-decay models (probabilities change as event approaches)
- Conditional probability models for correlated events
- Machine learning models trained on historical prediction market data

**Outputs:**
- Fair value estimate for each outcome (probability)
- Confidence intervals / uncertainty range
- Optimal bid/ask quotes at multiple size levels
- Real-time adjustment signals

#### 4.1.2 Order Management System (OMS)

**Requirements:**
- Multi-venue connectivity (Polymarket API, Kalshi API, on-chain DEXs)
- Support for both REST and WebSocket APIs
- EVM transaction management (for on-chain platforms like Polymarket)
- Order lifecycle management (create, amend, cancel, fill tracking)
- Cross-market position tracking
- Smart order routing across venues

**Polymarket-specific:**
- Polygon network transaction management
- Gas fee optimization
- CLOB client SDK integration
- Wallet/signer management for on-chain operations

**Kalshi-specific:**
- Traditional REST/WebSocket API
- USD settlement (no crypto wallet needed)
- Compliance with DCM participant rules

#### 4.1.3 Risk Management System

**Real-time requirements:**
- Per-market position limits and P&L tracking
- Portfolio-level risk aggregation across all prediction markets
- Correlation analysis between markets
- Maximum loss calculations per event category
- Inventory skew monitoring and automated quote adjustment
- Drawdown limits and circuit breakers

**Event-specific features:**
- Event calendar integration (know when events resolve)
- Pre-event risk reduction automation
- Settlement tracking and reconciliation
- Oracle dispute monitoring (for on-chain markets)

#### 4.1.4 Data Feeds & Analytics

**External Data Sources Required:**

| Category | Sources | Use Case |
|----------|---------|----------|
| **Polling data** | FiveThirtyEight, RealClearPolitics, polls APIs | Political markets |
| **Sports data** | ESPN, Sports Reference, odds aggregators | Sports markets |
| **Economic data** | FRED, BLS, Census Bureau | Economic indicator markets |
| **Weather data** | NOAA, weather APIs | Weather markets |
| **Crypto data** | Exchange APIs, on-chain analytics | Crypto price markets |
| **Sentiment** | Twitter/X API, Reddit, news NLP | All markets |
| **On-chain data** | Polygon RPC, blockchain indexers | Polymarket trade flow |
| **Competitor prices** | Polymarket CLOB, Kalshi, betting exchanges | Cross-market arbitrage |

#### 4.1.5 Settlement & Oracle Infrastructure

**For On-Chain Markets (Polymarket):**

**UMA Optimistic Oracle:**
- Default oracle for most Polymarket markets
- Process: Request -> Propose -> Dispute -> Vote
- Proposer submits answer with bond; liveness period allows disputes
- If disputed, UMA token holders vote on resolution
- Best for subjective/non-price markets (elections, policy decisions)
- Challenge: disputes can delay settlement

**Chainlink Data Streams:**
- Used for price-based prediction markets
- Sub-second latency data delivery (pull-based model)
- Combined with Chainlink Automation for auto-settlement
- Best for: crypto price markets, economic data markets
- Provides tamper-resistant, decentralized data

**Polymarket's approach in 2025:** Uses BOTH oracles:
- Chainlink for high-frequency, price-based markets
- UMA for diverse, subjective, and complex event markets

**For Regulated Markets (Kalshi):**
- Centralized settlement by the exchange
- Uses verified data sources (official statistics, AP race calls, etc.)
- No blockchain oracle dependency
- Settlement typically within hours of event resolution

### 4.2 Low-Latency Execution for On-Chain Markets

**Challenges specific to on-chain prediction markets:**
- Polygon block time: ~2 seconds
- Gas fee management and optimization
- MEV (Miner Extractable Value) protection
- Transaction confirmation uncertainty
- Nonce management for high-frequency trading

**Solutions:**
- Off-chain order matching with on-chain settlement (Polymarket's hybrid model)
- Priority gas fee bidding for critical transactions
- Flashbots/private mempool usage to prevent frontrunning
- Multi-wallet strategies for parallel transaction submission
- WebSocket connections for real-time order book updates

---

## 5. Existing Binance Infrastructure Mapping

### 5.1 Reusable Components

| Binance Component | Prediction Market Application | Reuse Potential |
|-------------------|-------------------------------|-----------------|
| **Matching Engine** | Core order matching for proprietary CLOB | **HIGH** - Proven at scale (1.4M+ orders/sec), direct applicability |
| **OTC Desk** | B2B liquidity provision to external prediction platforms | **HIGH** - RFQ workflows, bilateral pricing, institutional relationships |
| **Binance Convert (RFQ)** | B2C retail prediction market access (simple buy/sell interface) | **VERY HIGH** - Perfect model for retail prediction market shares |
| **Risk Management System** | Real-time position/exposure monitoring | **HIGH** - Needs adaptation for event-driven binary payoffs |
| **Binance Earn** | Structured products on prediction outcomes | **MEDIUM** - Yield-bearing prediction exposure products |
| **User infrastructure** | KYC/AML, wallets, payment rails | **VERY HIGH** - 200M+ registered users, existing compliance |
| **Binance Futures** | Derivatives pricing, margining, settlement | **MEDIUM** - Relevant for perpetual prediction contracts |
| **Data Infrastructure** | Market data aggregation and distribution | **HIGH** - Needs new data sources (polls, sports, etc.) |
| **API Platform** | Developer/institutional connectivity | **HIGH** - REST/WebSocket APIs already battle-tested |

### 5.2 Detailed Mapping

#### 5.2.1 Binance Convert as Prediction Market Interface

Binance Convert's RFQ (Request for Quote) model is **ideally suited** for retail prediction market access:

**Current Convert Model:**
1. User requests quote for crypto pair
2. System aggregates pricing from internal + external liquidity
3. User receives a fixed-price quote with expiry timer
4. User accepts or rejects; execution is guaranteed at quoted price

**Prediction Market Adaptation:**
1. User selects prediction market (e.g., "BTC > $100K by Dec 2026?")
2. User requests quote for YES or NO shares
3. Binance (as market maker) quotes price based on internal model + external market data
4. User sees: "Buy 100 YES shares at $0.65 each = $65.00" with expiry timer
5. User accepts; Binance fulfills from inventory or hedges externally
6. Settlement at event resolution

**Advantages of the Convert/RFQ model for predictions:**
- Simple UX for retail users (no order book complexity)
- Binance controls spread/margin
- No visible order book = less information leakage
- Guaranteed execution = better user experience
- Binance can aggregate pricing from Polymarket + Kalshi + internal models

#### 5.2.2 Binance OTC for B2B Liquidity

**Current OTC model:**
- Bilateral trading desk for large crypto transactions
- Institutional counterparties
- Custom pricing, block trades
- Settlement via Binance infrastructure

**Prediction Market Adaptation:**
- Provide bulk liquidity to external prediction platforms
- Quote block sizes of prediction shares to institutions/funds
- Offer hedging services: "We'll take the other side of your prediction portfolio"
- Provide custom event contract creation for institutional needs

#### 5.2.3 Binance Earn for Structured Prediction Products

**Potential Products:**
- "Prediction Yield Vault": Deposit USDT, earn yield from market-making spread on prediction markets
- "Event-Linked Notes": Principal-protected products with upside tied to prediction outcomes
- "Prediction Index": Basket of prediction market positions tracking major events

### 5.3 Components Requiring New Development

| Component | Description | Build Complexity |
|-----------|-------------|-----------------|
| **Prediction Pricing Engine** | Fair value models for event probabilities | HIGH - Requires domain expertise |
| **External Data Integration** | Polling, sports, economic data feeds | MEDIUM |
| **Oracle Integration** | UMA/Chainlink connectivity for on-chain settlement | MEDIUM |
| **Event Management System** | Create, manage, resolve prediction markets | HIGH |
| **Domain-Specific Risk Models** | Event risk, information asymmetry detection | HIGH |
| **Cross-Platform Connectivity** | APIs to Polymarket, Kalshi, etc. for hedging | MEDIUM |
| **Regulatory Compliance Layer** | CFTC/DCM compliance for US markets | HIGH |

---

## 6. Competitive Landscape

### 6.1 Active Market Makers in Prediction Markets

#### 6.1.1 Susquehanna International Group (SIG)

- **Role:** First dedicated institutional market maker on Kalshi (April 2024)
- **Activities:**
  - Subsidiary "Susquehanna Government Products, LLLP" provides liquidity on Kalshi
  - Joint venture with Robinhood to launch new DCM exchange (2026)
  - Will be "day-one liquidity provider" for Robinhood's new exchange
  - Acquisition of MIAXdx (CFTC-licensed DCM) with Robinhood
- **Significance:** Brought institutional-grade liquidity to prediction markets for the first time

#### 6.1.2 Jump Trading

- **Role:** Strategic liquidity provider for Polymarket
- **Activities:**
  - Acquiring minority equity stake in Polymarket
  - "Equity-for-liquidity" arrangement: stake scales with liquidity provided
  - Provides deep order book liquidity on Polymarket's CLOB
- **Significance:** First major prop trading firm to take equity in a prediction market platform

#### 6.1.3 Wintermute

- **Role:** Expanding presence in prediction market ecosystem
- **Activities:**
  - Launched "OutcomeMarket" prediction platform with Chaos Labs (Sept 2024)
  - Focused initially on U.S. presidential election markets
  - Active analysis and reporting on prediction market capital flows
  - Positioning as liquidity provider across the prediction market sector
- **Significance:** First major crypto market maker to launch its own prediction platform

#### 6.1.4 Citadel Securities

- **Role:** Exploring entry into prediction markets
- **Activities:**
  - CEO Peng Zhao participated in Kalshi funding round (June 2025)
  - Reports of Citadel exploring launching own platform or investing in existing one (late 2025)
  - No official confirmation of direct market-making activity yet
- **Significance:** Potential entry of the world's largest market maker could transform the space

### 6.2 Platform Operator Partnerships

| Platform | Key MM Partner | Model | Notes |
|----------|---------------|-------|-------|
| **Polymarket** | Jump Trading | Equity-for-liquidity | Jump takes equity stake proportional to liquidity |
| **Kalshi** | Susquehanna (SIG) | Designated MM program | Formal DMM with reduced fees, enhanced limits |
| **Robinhood (new exchange)** | Susquehanna (SIG) | Joint venture | SIG as day-one LP; Robinhood controlling partner |
| **Coinbase** | Via Kalshi integration | Distribution partnership | Coinbase distributes Kalshi markets to users |
| **Wintermute** | Own platform (OutcomeMarket) | Vertically integrated | MM + platform operator in one |

### 6.3 Coinbase-Kalshi Partnership Details

**Structure:**
- Coinbase integrates Kalshi's regulated prediction markets into Coinbase app
- Contracts denominated in USDC, custodied on Coinbase
- Kalshi provides the regulated exchange infrastructure (DCM license)
- Coinbase provides distribution (user base) and crypto payment rails
- Market making provided by Kalshi's existing DMM network (Susquehanna et al.)
- Not a direct market-making relationship; more of a distribution/front-end partnership

**Strategic Implications:**
- Demonstrates "exchange as distributor" model
- Kalshi handles regulation; Coinbase handles user acquisition
- USDC integration bridges crypto and prediction markets
- Co-founded Coalition for Prediction Markets (Dec 2025) with Robinhood, Crypto.com, Underdog

---

## 7. Market Opportunities & Business Models

### 7.1 Business Model Options for Binance

#### Model A: B2C -- Binance as Market Maker Quoting to Retail Users

**Description:** Binance quotes prediction market shares directly to its 200M+ user base through a Convert-like interface.

**Revenue Streams:**
- Spread income: 2-5 cents per share on each trade
- Platform fees: 1-2% transaction fee
- Information edge: proprietary probability models for better pricing

**Implementation:**
- Front-end: Binance Convert-style RFQ interface
- Back-end: Binance acts as principal market maker
- Hedging: Real-time hedging on Polymarket/Kalshi
- Settlement: On-platform, with backend oracle/exchange settlement

**Revenue Estimate:**
- Assume 5% market share of global prediction market volume = $2.2B annually
- Average spread of 3 cents per $1 notional = $66M spread revenue
- Plus 1% fees = $22M fee revenue
- Total: ~$88M/year at 5% market share

**Pros:** High margin, direct user relationship, data advantage
**Cons:** Principal risk, regulatory complexity, requires pricing engine

#### Model B: B2B -- Binance Providing Liquidity to External Platforms

**Description:** Binance OTC desk provides bulk liquidity to prediction market platforms.

**Revenue Streams:**
- OTC spread on block trades
- Liquidity provision fees/rebates from platforms
- Equity stakes (Jump Trading model)

**Implementation:**
- Use existing OTC desk infrastructure
- Connect to Polymarket and Kalshi APIs
- Deploy algorithmic market making strategies
- Offer white-glove service to institutional prediction market traders

**Revenue Estimate:**
- Target $500M-1B in monthly liquidity provision
- Earn 1-3 bps on facilitated volume = $6-36M/year

**Pros:** Lower risk, leverages existing OTC infrastructure
**Cons:** Lower margin, dependent on platform relationships

#### Model C: White-Label Prediction Market Infrastructure

**Description:** Binance provides matching engine + market making + settlement infrastructure to third parties.

**Revenue Streams:**
- Licensing fees for matching engine technology
- Revenue share on transaction volume
- Market-making-as-a-service fees

**Potential Clients:**
- Regional exchanges wanting to add prediction markets
- Media companies wanting branded prediction features
- Sports betting operators seeking CFTC-regulated structure
- Web3 projects wanting prediction market functionality

**Revenue Estimate:**
- License fees: $1-5M per client
- Revenue share: 10-20% of platform fees
- Market making: spread income on facilitated volume

**Pros:** Recurring revenue, scalable, platform-agnostic
**Cons:** Requires significant build-out, long sales cycle

#### Model D: Hybrid -- Full Vertical Integration

**Description:** Binance operates its own prediction market exchange with integrated market making, similar to what CZ is already doing on BNB Chain.

**Components:**
- Own prediction market platform (or acquire/invest in existing)
- Integrated market making using Binance's capital
- Distribution through Binance app to 200M+ users
- Settlement via BNB Chain or Polygon
- Potential for regulated US offering via DCM acquisition (like Robinhood/MIAXdx model)

**Revenue Streams:**
- Transaction fees
- Market-making spread
- Data licensing
- Token economics (if applicable)

### 7.2 Revenue Model Comparison

| Revenue Source | Model A (B2C) | Model B (B2B) | Model C (White-Label) | Model D (Integrated) |
|---------------|---------------|---------------|----------------------|---------------------|
| Spread income | +++ | ++ | + | +++ |
| Transaction fees | ++ | - | + | +++ |
| Rebates/incentives | + | ++ | - | - |
| Licensing | - | - | +++ | + |
| Information edge | +++ | + | + | +++ |
| Token/platform value | + | - | + | +++ |
| **Risk Level** | Medium-High | Low-Medium | Low | High |
| **Capital Required** | Medium | Low | Medium | High |
| **Time to Launch** | 6-9 months | 3-6 months | 9-12 months | 12-18 months |

### 7.3 CZ/Binance Ecosystem Current Activity

Binance is **already involved** in prediction markets through CZ's ecosystem:

- **Opinion Lab:** CZ-backed prediction market on BNB Chain (launched Oct 2025), quickly gained significant volume
- **predict.fun:** Another BNB Chain prediction platform introduced by CZ (Dec 2025)
- **Trust Wallet:** Integrated prediction trading via partnerships with Polymarket and Kalshi
- **Binance Futures:** Event-based derivative contracts already available
- **Binance Research:** Published reports on prediction market growth trends for 2026

This suggests a **phased strategy** is already underway:
1. Phase 1 (Done): Ecosystem investments and integrations
2. Phase 2 (Current): BNB Chain native prediction platforms
3. Phase 3 (Opportunity): Binance-native prediction market making

---

## 8. Regulatory Considerations

### 8.1 US Regulatory Framework (CFTC)

#### 8.1.1 Current State (as of Feb 2026)

**CFTC Jurisdiction:**
- Prediction markets operating as event contracts fall under CFTC jurisdiction
- Kalshi operates as a **Designated Contract Market (DCM)** -- the gold standard for regulation
- New CFTC Chairman Michael S. Selig (appointed late 2025) strongly supports federal jurisdiction
- In January 2026, CFTC withdrew proposed ban on political and sports event contracts
- CFTC is drafting new rules to establish "clear standards" for prediction markets
- CFTC filed amicus brief reaffirming "exclusive jurisdiction" over commodity derivatives including prediction markets

#### 8.1.2 Designated Market Maker (DMM) Obligations

On CFTC-regulated platforms like Kalshi, designated market makers have specific obligations:

**Requirements to become a DMM:**
- Rigorous review of financial resources
- Demonstrated relevant experience
- Business reputation assessment
- Ongoing capital adequacy requirements

**Obligations:**
- Maintain continuous two-sided quotes during market hours
- Meet minimum quoting obligations (% of time with active quotes)
- Comply with position reporting requirements
- Maintain orderly markets during high volatility
- Adhere to anti-manipulation rules

**Benefits:**
- Reduced transaction fees
- Higher position limits
- Enhanced API access
- Priority in market data

#### 8.1.3 Federal vs. State Conflict

**Key Tension:**
- Multiple states (Massachusetts, Nevada, etc.) have filed lawsuits against Kalshi
- States argue sports event contracts = unlicensed sports betting = state jurisdiction
- CFTC asserts exclusive federal jurisdiction over all commodity/event contracts
- May ultimately require Supreme Court resolution

**Coalition for Prediction Markets (CPM):**
- Founded December 2025
- Members: Kalshi, Coinbase, Robinhood, Crypto.com, Underdog
- CEO: Former Congressman Sean Patrick Maloney
- Senior Advisor: Former Congressman Patrick McHenry
- Mission: Preserve federal CFTC framework, prevent state-level gambling classification
- Advocates prediction markets are financial instruments, not gambling

### 8.2 Implications for Binance

**Challenges:**
- Binance has complex regulatory history in the US (2023 settlement)
- Operating as or through a DCM requires CFTC licensing
- May need to partner with existing licensed entity (similar to Coinbase-Kalshi model)
- Cross-border considerations for non-US users

**Possible Approaches:**
1. **Partner model:** Integrate an existing DCM's markets (like Coinbase did with Kalshi)
2. **Acquisition model:** Acquire a DCM license (like Robinhood acquiring MIAXdx)
3. **International-first:** Launch in jurisdictions where prediction markets face less regulation
4. **BNB Chain native:** Operate decentralized prediction markets via BNB Chain (already in progress via Opinion Lab, predict.fun)

### 8.3 International Regulatory Landscape

| Jurisdiction | Status | Notes |
|-------------|--------|-------|
| **United States** | CFTC-regulated (DCM framework) | Most developed regulatory framework; federal-state tension |
| **European Union** | MiCA framework applies | Event contracts may fall under derivatives regulation |
| **United Kingdom** | FCA oversight possible | Gambling Commission may also claim jurisdiction |
| **Singapore** | MAS oversight | Generally crypto-friendly; prediction markets in gray area |
| **Dubai/UAE** | DFSA/ADGM frameworks | Crypto-friendly; potential for prediction market licensing |
| **Japan** | FSA regulated | Strict gambling laws; limited prediction market activity |
| **Decentralized** | No jurisdiction | Polymarket operates from Panama; accessible globally |

---

## 9. Strategic Recommendations for Binance

### 9.1 Recommended Phased Approach

#### Phase 1: B2B Liquidity Provision (3-6 months)
- Deploy algorithmic market making on Polymarket via existing OTC desk
- Become a liquidity provider on Kalshi's DMM program
- Build cross-platform connectivity and hedging infrastructure
- Accumulate operational experience and data
- **Capital:** $50-100M dedicated trading capital
- **Revenue target:** $20-40M/year

#### Phase 2: B2C via Convert Interface (6-12 months)
- Launch "Binance Predict" as a Convert-style interface
- Binance acts as principal market maker for retail users
- Quote prices based on external market aggregation + internal models
- Start with high-volume markets (sports, crypto price, elections)
- Integrate with Binance app for 200M+ user distribution
- **Capital:** $100-200M for market making
- **Revenue target:** $50-100M/year

#### Phase 3: Full Platform (12-18 months)
- Launch own prediction market CLOB on BNB Chain or proprietary infrastructure
- Attract external market makers to platform
- Offer white-label infrastructure to partners
- Pursue regulatory licenses where appropriate
- **Capital:** $200-500M for platform + market making
- **Revenue target:** $100-250M/year

### 9.2 Critical Success Factors

1. **Pricing Engine Quality:** The ability to accurately model event probabilities is the core competitive advantage
2. **Regulatory Strategy:** Clear jurisdictional approach (US partnership vs. international-first)
3. **Data Advantage:** Leverage Binance's massive user data and trading flow for better probability estimation
4. **Capital Efficiency:** Prediction market making ties up capital until event resolution; efficient capital allocation is key
5. **User Experience:** Simplify prediction trading for retail (Convert model is ideal)
6. **Speed to Market:** The landscape is consolidating rapidly; early mover advantage matters

### 9.3 Key Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Regulatory prohibition in key markets | Medium | High | Multi-jurisdiction approach |
| Sustained losses from event risk | Medium | Medium | Portfolio diversification, position limits |
| Competition from established MMs (Susquehanna, Jump) | High | Medium | Leverage Binance's user base and capital |
| Oracle/settlement failures | Low | High | Dual oracle strategy (Chainlink + UMA) |
| Reputational risk from association with "gambling" | Medium | Medium | Position as "event trading" / financial innovation |
| Capital lock-up in long-dated markets | Medium | Low | Focus on short-dated events |

---

## Appendix A: Key Data Points Summary

| Metric | 2024 | 2025 | 2026 (Projected) |
|--------|------|------|-------------------|
| Global prediction market volume | ~$9B | ~$44B | $80-100B+ |
| Polymarket volume | ~$9B (cumulative) | $21.5B | Growing |
| Kalshi volume | N/A (early) | $24B | Growing |
| Kalshi fee revenue | N/A | $263.5M | Growing |
| Active users (global) | ~5M | ~15M | ~30M+ |
| VC funding | ~$100M | $3.7B | Growing |
| Polymarket valuation | ~$1B | $9B (ICE $2B investment) | TBD |
| Kalshi valuation | ~$1B | $11B | TBD |

## Appendix B: Key Players Quick Reference

| Entity | Role | Activity |
|--------|------|----------|
| **Polymarket** | Leading on-chain prediction market | $21.5B volume 2025; CLOB on Polygon; UMA+Chainlink oracles |
| **Kalshi** | Leading regulated prediction market | $24B volume 2025; CFTC DCM; sports-dominated |
| **Susquehanna (SIG)** | First institutional DMM on Kalshi | JV with Robinhood for new DCM exchange |
| **Jump Trading** | Strategic LP for Polymarket | Equity stake in Polymarket |
| **Wintermute** | Crypto MM entering predictions | Launched OutcomeMarket platform |
| **Citadel Securities** | Exploring entry | CEO invested in Kalshi round |
| **Coinbase** | Distribution partner for Kalshi | USDC integration; CPM co-founder |
| **Robinhood** | Fastest-growing prediction product | JV with SIG to launch DCM; 9B+ contracts traded |
| **ICE (NYSE parent)** | Strategic investor | $2B invested in Polymarket at $9B valuation |
| **CZ/Binance ecosystem** | BNB Chain prediction platforms | Opinion Lab, predict.fun, Trust Wallet integration |
| **UMA** | Optimistic Oracle provider | Primary oracle for Polymarket non-price markets |
| **Chainlink** | Data Streams oracle provider | Used for Polymarket price-based markets |
| **CFTC** | US federal regulator | Asserting exclusive jurisdiction; drafting new rules |
| **Coalition for Prediction Markets** | Industry lobbying group | Kalshi, Coinbase, Robinhood, Crypto.com, Underdog |

---

*This analysis is based on web research conducted on 2026-02-24. Data points reflect information available through public sources as of this date.*
