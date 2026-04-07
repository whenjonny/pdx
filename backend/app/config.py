from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Blockchain
    rpc_url: str = "http://localhost:8545"
    chain_id: int = 84532  # Base Sepolia

    # Contract addresses (set after deployment)
    pdx_market_address: str = ""
    mock_usdc_address: str = ""
    pdx_oracle_address: str = ""
    deploy_block: int = 0  # Block number when contracts were deployed (for event queries)

    # Deployer private key (for backend write operations - anvil account 0)
    deployer_private_key: str = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

    # ABI directory
    abi_dir: str = str(Path(__file__).parent.parent.parent / "contracts" / "abi")

    # SQLite database path
    db_path: str = str(Path(__file__).parent.parent / "data" / "pdx.db")

    # IPFS / Pinata (optional for MVP)
    pinata_api_key: str = ""
    pinata_secret_key: str = ""
    pinata_gateway_url: str = "https://gateway.pinata.cloud/ipfs"

    # MiroFish
    mirofish_url: str = "http://localhost:5001"
    use_mock_mirofish: bool = True  # Use mock by default

    # MiroFish LLM settings
    mirofish_llm_api_key: str = ""  # empty = heuristic mode
    mirofish_llm_base_url: str = "https://api.openai.com/v1"
    mirofish_llm_model: str = "gpt-4o-mini"
    mirofish_interval_seconds: int = 300  # 5 minutes

    # Server
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
