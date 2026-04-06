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

    # ABI directory
    abi_dir: str = str(Path(__file__).parent.parent.parent / "contracts" / "abi")

    # IPFS / Pinata (optional for MVP)
    pinata_api_key: str = ""
    pinata_secret_key: str = ""

    # MiroFish
    mirofish_url: str = "http://localhost:5001"
    use_mock_mirofish: bool = True  # Use mock by default

    # Server
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
