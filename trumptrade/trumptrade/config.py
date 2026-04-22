from __future__ import annotations
import os
from pathlib import Path
import yaml

_DEFAULT_PLAYBOOK_PATH = Path(__file__).resolve().parent.parent / "config" / "trump_policy_playbook.yaml"


def playbook_path() -> Path:
    env = os.environ.get("TRUMPTRADE_PLAYBOOK")
    if env:
        return Path(env)
    return _DEFAULT_PLAYBOOK_PATH


def data_dir() -> Path:
    d = Path(os.environ.get("TRUMPTRADE_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_playbook(path: Path | None = None) -> dict:
    p = path or playbook_path()
    with open(p, "r") as f:
        return yaml.safe_load(f)
