"""Default configuration for PDX SDK."""

from __future__ import annotations

import os
from pathlib import Path

# Default ABI directory: <sdk>/../contracts/abi/
DEFAULT_ABI_DIR = str(
    Path(__file__).resolve().parent.parent.parent / "contracts" / "abi"
)

DEFAULT_BACKEND_URL = "http://localhost:8000"

# Maximum uint256 used for unlimited approvals.
MAX_UINT256 = 2**256 - 1
