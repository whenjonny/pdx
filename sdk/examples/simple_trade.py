"""Simple trading example -- buy YES on a market."""

import os

from dotenv import load_dotenv

from pdx_sdk import PDXClient

load_dotenv()

client = PDXClient(
    rpc_url=os.getenv("RPC_URL", "http://localhost:8545"),
    private_key=os.getenv("PRIVATE_KEY"),
    market_address=os.getenv("PDX_MARKET"),
    usdc_address=os.getenv("MOCK_USDC"),
)

# Mint and approve USDC
client.mint_usdc(10_000 * 10**6)
client.approve_usdc()

# Get market info
market = client.get_market(0)
print(f"Market: {market.question}")
print(f"YES price: {market.priceYes / 1e6:.2%}")

# Buy YES
result = client.buy_yes(0, 1000 * 10**6)
print(f"Bought YES! tx: {result.tx_hash}")

# Check updated price
market = client.get_market(0)
print(f"New YES price: {market.priceYes / 1e6:.2%}")
