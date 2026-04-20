"""Full agent workflow: evidence search -> compute -> trade -> redeem."""

import os

from dotenv import load_dotenv

from pdx_sdk import PDXClient
from pdx_sdk.evidence import format_evidence, mock_upload

load_dotenv()

client = PDXClient(
    rpc_url=os.getenv("RPC_URL", "http://localhost:8545"),
    private_key=os.getenv("PRIVATE_KEY"),
    market_address=os.getenv("PDX_MARKET"),
    usdc_address=os.getenv("MOCK_USDC"),
)

# ------------------------------------------------------------------
# 1. Setup -- mint & approve USDC
# ------------------------------------------------------------------
print("=== Setup ===")
client.mint_usdc(50_000 * 10**6)
client.approve_usdc()
balance = client.get_usdc_balance()
print(f"USDC balance: {balance / 1e6:,.2f}")

# ------------------------------------------------------------------
# 2. Read market
# ------------------------------------------------------------------
print("\n=== Market Info ===")
market = client.get_market(0)
print(f"Market #{market.id}: {market.question}")
print(f"  YES price : {market.priceYes / 1e6:.4f}")
print(f"  NO  price : {market.priceNo / 1e6:.4f}")
print(f"  Deadline  : {market.deadline}")

# ------------------------------------------------------------------
# 3. Compute embedding for analysis text
# ------------------------------------------------------------------
print("\n=== Compute Embedding ===")
analysis_text = (
    "Based on recent macroeconomic data and policy announcements, "
    "the probability of this outcome has increased significantly."
)
embedding = client.compute_embedding(analysis_text)
print(f"Embedding dim: {len(embedding)}, first 5: {embedding[:5]}")

# ------------------------------------------------------------------
# 4. Monte Carlo simulation
# ------------------------------------------------------------------
print("\n=== Monte Carlo Simulation ===")
prior = market.priceYes / 1e6  # use current market price as prior
evidence_scores = [0.3, 0.5, -0.1]  # simulated evidence scores
weights = [0.4, 0.4, 0.2]

mc = client.run_monte_carlo(prior, evidence_scores, weights, n_sim=10_000)
print(f"MC mean: {mc.mean:.4f}")
print(f"MC std:  {mc.std:.4f}")
print(f"MC 95%CI: [{mc.ci_95_lower:.4f}, {mc.ci_95_upper:.4f}]")

# ------------------------------------------------------------------
# 5. Format and submit evidence
# ------------------------------------------------------------------
print("\n=== Submit Evidence ===")
evidence_payload = format_evidence(
    market_id=0,
    direction="YES",
    confidence=mc.mean,
    sources=["https://example.com/data-source-1", "https://example.com/data-source-2"],
    analysis=analysis_text,
    generated_by="pdx-demo-agent",
)

# Use mock upload for local testing (no backend needed)
ipfs_hash = mock_upload(evidence_payload)
print(f"Mock IPFS hash: {ipfs_hash}")

result = client.submit_evidence(0, ipfs_hash, f"Agent prediction: YES @ {mc.mean:.2%}")
print(f"Evidence submitted! tx: {result.tx_hash}")

# ------------------------------------------------------------------
# 6. Trade based on simulation result
# ------------------------------------------------------------------
print("\n=== Trade ===")
trade_amount = 2_000 * 10**6  # 2000 USDC
if mc.mean > 0.55:
    print(f"MC says YES ({mc.mean:.2%}) -- buying YES tokens")
    result = client.buy_yes(0, trade_amount)
elif mc.mean < 0.45:
    print(f"MC says NO ({mc.mean:.2%}) -- buying NO tokens")
    result = client.buy_no(0, trade_amount)
else:
    print(f"MC is indecisive ({mc.mean:.2%}) -- no trade")
    result = None

if result:
    print(f"Trade tx: {result.tx_hash}")
    print(f"Tokens received: {result.tokens_amount / 1e6:,.2f}")
    print(f"Fee paid: {result.fee / 1e6:,.2f}")

# ------------------------------------------------------------------
# 7. Portfolio summary
# ------------------------------------------------------------------
print("\n=== Portfolio ===")
updated = client.get_market(0)
print(f"Updated YES price: {updated.priceYes / 1e6:.4f}")
print(f"Updated NO  price: {updated.priceNo / 1e6:.4f}")
print(f"USDC balance: {client.get_usdc_balance() / 1e6:,.2f}")

# Existing evidence
evidence_list = client.get_evidence(0)
print(f"\nEvidence count: {len(evidence_list)}")
for i, ev in enumerate(evidence_list):
    print(f"  [{i}] {ev.summary} (by {ev.submitter[:10]}...)")
