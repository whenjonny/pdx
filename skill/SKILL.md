---
name: pdx-predict
description: "PDX Prediction Market Agent - Research, analyze, submit V2 evidence, and generate MetaMask signing links for trades on Base L2"
version: 0.2.0
user-invocable: true
metadata: {"openclaw": {"requires": {"bins": ["python3"], "env": ["PDX_BACKEND_URL"], "python_packages": ["pdx-sdk>=0.1.0", "numpy>=1.24.0", "sentence-transformers>=2.2.0"]}, "primaryEnv": "PDX_BACKEND_URL"}}
---

# PDX Prediction Market Agent

An AI-powered agent for the PDX evidence-driven prediction market on Base L2.  Browse markets, research evidence, run local compute (embedding + Monte Carlo), submit V2 preprocessed evidence to IPFS, and generate MetaMask signing links for trades.

**The agent never touches private keys.**  All on-chain transactions are signed by the user through MetaMask via the PDX frontend `/sign` page.

## Architecture

```
Agent analyzes → builds transaction → generates signing URL
  → User clicks URL → MetaMask pops up → User confirms
```

PDX uses a CPMM AMM where users trade YES/NO outcome tokens with USDC.  Evidence submitted to the market unlocks a reduced trading fee (0.10% vs 0.30%) and feeds the MiroFish AI prediction engine.

**V2 Evidence Flow**: This agent submits preprocessed evidence (384-dim embeddings + Monte Carlo simulations) to IPFS.  The MiroFish backend aggregates V2 data mathematically -- no LLM needed.

## Setup

```bash
pip install pdx-sdk
export PDX_BACKEND_URL="http://localhost:8000"   # Backend API
export PDX_FRONTEND_URL="http://localhost:5173"  # Frontend (for signing URLs)
```

No private keys or wallet addresses needed.  The user signs transactions in their browser via MetaMask.

## Commands

### /pdx-markets

Browse all active prediction markets.

1. Fetch markets from the backend API:

```python
import requests, os

backend = os.environ.get("PDX_BACKEND_URL", "http://localhost:8000")
markets = requests.get(f"{backend}/api/markets").json()

for m in markets:
    if not m["resolved"]:
        pred = requests.get(f"{backend}/api/predictions/{m['id']}").json()
        print(f"Market #{m['id']}: {m['question']}")
        print(f"  YES: {m['priceYes']:.1%}  NO: {m['priceNo']:.1%}")
        print(f"  MiroFish: {pred['probability_yes']:.1%} (conf: {pred['confidence']:.0%})")
        print(f"  Evidence: {m['evidenceCount']}")
```

2. Present as a table: ID | Question | YES Price | MiroFish Prob | Evidence Count
3. Highlight markets where MiroFish diverges >15% from AMM price (trading opportunities)

### /pdx-analyze <market_id>

Deep analysis on a specific market.  Generates a V2-ready evidence package with local compute.

1. Fetch market details and existing evidence:

```python
import requests, os

backend = os.environ.get("PDX_BACKEND_URL", "http://localhost:8000")
market = requests.get(f"{backend}/api/markets/{<market_id>}").json()
evidence = requests.get(f"{backend}/api/evidence/{<market_id>}").json()
```

2. Search the web for relevant, recent information:
   - **Breadth**: Major news outlets (Reuters, AP, Bloomberg, BBC)
   - **Domain**: Specialized sources for the topic
   - **Contrarian**: Actively search for counter-evidence

3. Assess source credibility using `{baseDir}/references/credibility_sources.md`:
   - Tier 1 (8-10): Academic journals, wire services, official institutions
   - Tier 2 (5-7): Quality newspapers, tech outlets
   - Tier 3 (1-4): Social media, blogs

4. Synthesize into structured analysis:
   - **Claim**: Main thesis
   - **Supporting points**: Evidence favoring YES (with credibility scores)
   - **Counter points**: Evidence favoring NO (with credibility scores)
   - **Net sentiment**: -1.0 (strong NO) to +1.0 (strong YES)
   - **Direction**: YES or NO

5. Run local compute:

```python
from pdx_sdk.compute import compute_embedding, run_monte_carlo

embedding = compute_embedding("<analysis_text>")
mc = run_monte_carlo(
    prior_yes=market["priceYes"],
    evidence_scores=[<net_sentiment>],
    n_sim=5000,
)
print(f"MC: mean={mc.mean:.2%}, 95% CI=[{mc.ci_95_lower:.2%}, {mc.ci_95_upper:.2%}]")
```

6. Present the full report with trading recommendation:
   - BUY YES if MC mean > AMM price + 5%
   - BUY NO if MC mean < AMM price - 5%
   - HOLD otherwise

### /pdx-submit <market_id> --direction YES|NO

Submit V2 evidence to IPFS, then generate a MetaMask signing link for the on-chain submission.

**Prerequisite**: Run `/pdx-analyze <market_id>` first.

1. Package analysis into V2 format and upload to IPFS:

```python
from pdx_sdk.evidence import format_evidence_v2, upload_to_ipfs_v2

evidence_payload = format_evidence_v2(
    market_id=<market_id>,
    direction="<YES|NO>",
    text="<analysis_text>",
    sources=[{"url": "<url>", "title": "<title>", "credibility": <score>}],
    analysis="<structured_claim>",
    prior_yes=market["priceYes"],
    evidence_score=<net_sentiment>,
    generated_by="openclaw-pdx-agent",
)

cid = upload_to_ipfs_v2(evidence_payload)
print(f"Evidence uploaded to IPFS: {cid}")
```

2. Generate the signing URL for the user:

```python
import hashlib
from pdx_sdk.signing import build_evidence_url

ipfs_hash = "0x" + hashlib.sha256(cid.encode()).hexdigest()
summary = f"{evidence_payload['direction']}: {evidence_payload['structuredAnalysis']['claim'][:100]}"

url = build_evidence_url(
    market_id=<market_id>,
    direction="<YES|NO>",
    ipfs_hash=ipfs_hash,
    summary=summary,
    source="MiroFish Agent",
)
print(f"Sign this transaction in MetaMask:")
print(url)
```

3. Present to the user:
   - IPFS CID for verification
   - The signing URL as a clickable link
   - Explain: "Click the link to open MetaMask and confirm the evidence submission. This unlocks the 0.10% trading fee discount."

### /pdx-trade <market_id> --amount <usdc> [--direction YES|NO]

Generate a MetaMask signing link for a trade.  The agent does NOT execute the trade -- the user signs it.

1. Determine direction from the most recent `/pdx-analyze` if not specified:
   - MC mean > AMM + 5% → YES
   - MC mean < AMM - 5% → NO
   - Otherwise → warn the user the spread is narrow

2. Generate the signing URL:

```python
from pdx_sdk.signing import build_buy_url

url = build_buy_url(
    market_id=<market_id>,
    direction="<YES|NO>",
    amount="<usdc_amount>",
    source="MiroFish Agent",
)
print(f"Sign this trade in MetaMask:")
print(url)
```

3. Present to the user:
   - Transaction summary: "Buy YES/NO on Market #X for Y USDC"
   - The signing URL as a clickable link
   - Note: "The /sign page will handle USDC approval automatically if needed."
   - Remind: "Review the transaction carefully in MetaMask before confirming."

### /pdx-portfolio

View current portfolio.  This reads public on-chain data -- no wallet connection needed.

1. Fetch market data:

```python
import requests, os

backend = os.environ.get("PDX_BACKEND_URL", "http://localhost:8000")
markets = requests.get(f"{backend}/api/markets").json()

for m in markets:
    print(f"Market #{m['id']}: {m['question']}")
    print(f"  YES: {m['priceYes']:.1%}  NO: {m['priceNo']:.1%}")
    print(f"  Evidence: {m['evidenceCount']}")
    if m["resolved"]:
        print(f"  RESOLVED: {'YES' if m['outcome'] else 'NO'}")
```

2. Tell the user: "To see your token balances, visit the PDX frontend at {PDX_FRONTEND_URL}/portfolio and connect your wallet."

## Security Model

```
What the agent CAN do:           What the agent CANNOT do:
- Read market data (public)       - Sign transactions
- Search the web for evidence     - Access private keys
- Compute embeddings locally      - Move funds
- Run Monte Carlo simulations     - Execute trades
- Upload evidence to IPFS         - Approve token spending
- Generate signing URLs           - Access the user's wallet
```

The agent generates URLs pointing to the PDX frontend `/sign` page.  When the user clicks a URL:
1. The page opens in their browser
2. MetaMask pops up showing the transaction details
3. The user reviews and confirms (or rejects)
4. The transaction is signed locally and sent to the chain

## V2 Evidence Format

V2 evidence includes preprocessed data for instant MiroFish aggregation:

| Field | Type | Purpose |
|-------|------|---------|
| embedding | float[384] | Semantic similarity clustering |
| monteCarlo | {mean, std, ci_95} | Probability distribution |
| structuredAnalysis | {claim, points} | Machine-parseable analysis |
| sources | [{url, credibility}] | Weighted source reliability |

## Network

- **Chain**: Base L2 (Coinbase)
- **Token**: USDC (6 decimals)
- **Gas**: < $0.01 per transaction
- **IPFS**: Pinata for evidence storage
- **Compute**: Local CPU via pdx-sdk
- **Signing**: MetaMask via PDX frontend `/sign` page
