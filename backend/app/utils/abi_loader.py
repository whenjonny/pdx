import json
from pathlib import Path
from app.config import settings


def load_abi(contract_name: str) -> list:
    """Load contract ABI from the abi directory."""
    abi_path = Path(settings.abi_dir) / f"{contract_name}.json"
    with open(abi_path) as f:
        return json.load(f)
