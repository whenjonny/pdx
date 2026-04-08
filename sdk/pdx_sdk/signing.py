"""Build frontend signing URLs for agent-prepared transactions.

Instead of signing transactions directly (which requires a private key),
agents use these helpers to generate URLs that open the PDX frontend's
``/sign`` page.  The user clicks the link, MetaMask pops up, and the
user confirms the transaction themselves.

The agent never touches private keys.
"""

from __future__ import annotations

from urllib.parse import urlencode

from pdx_sdk.config import DEFAULT_FRONTEND_URL


def build_sign_url(
    action: str,
    market_id: int,
    *,
    amount: str = "",
    direction: str = "",
    ipfs_hash: str = "",
    summary: str = "",
    token_amount: str = "",
    source: str = "PDX Agent",
    frontend_url: str = DEFAULT_FRONTEND_URL,
) -> str:
    """Build a URL that opens the PDX frontend ``/sign`` page.

    Parameters
    ----------
    action : str
        One of: ``buyYes``, ``buyNo``, ``sell``, ``redeem``, ``submitEvidence``.
    market_id : int
        The on-chain market ID.
    amount : str
        USDC amount in human-readable units (e.g. ``"100"`` for 100 USDC).
        Required for ``buyYes`` / ``buyNo``.
    direction : str
        ``"YES"`` or ``"NO"``.  Required for ``sell`` and ``submitEvidence``.
    ipfs_hash : str
        The ``0x``-prefixed bytes32 evidence hash.  For ``submitEvidence``.
    summary : str
        On-chain summary string.  For ``submitEvidence``.
    token_amount : str
        Token amount for sell orders (human-readable).
    source : str
        Label shown on the signing page (e.g. ``"MiroFish Agent"``).
    frontend_url : str
        Base URL of the PDX frontend (default ``http://localhost:5173``).

    Returns
    -------
    str
        Full URL with query parameters that the user can click/open.
    """
    params: dict[str, str] = {
        "action": action,
        "marketId": str(market_id),
    }
    if amount:
        params["amount"] = amount
    if direction:
        params["direction"] = direction.upper()
    if ipfs_hash:
        params["ipfsHash"] = ipfs_hash
    if summary:
        params["summary"] = summary
    if token_amount:
        params["tokenAmount"] = token_amount
    if source:
        params["source"] = source

    base = frontend_url.rstrip("/")
    return f"{base}/sign?{urlencode(params)}"


def build_buy_url(
    market_id: int,
    direction: str,
    amount: str,
    *,
    source: str = "PDX Agent",
    frontend_url: str = DEFAULT_FRONTEND_URL,
) -> str:
    """Shortcut to build a buy YES/NO signing URL."""
    action = "buyYes" if direction.upper() == "YES" else "buyNo"
    return build_sign_url(
        action, market_id,
        amount=amount, direction=direction,
        source=source, frontend_url=frontend_url,
    )


def build_sell_url(
    market_id: int,
    direction: str,
    token_amount: str,
    *,
    source: str = "PDX Agent",
    frontend_url: str = DEFAULT_FRONTEND_URL,
) -> str:
    """Shortcut to build a sell signing URL."""
    return build_sign_url(
        "sell", market_id,
        direction=direction, token_amount=token_amount,
        source=source, frontend_url=frontend_url,
    )


def build_evidence_url(
    market_id: int,
    direction: str,
    ipfs_hash: str,
    summary: str,
    *,
    source: str = "PDX Agent",
    frontend_url: str = DEFAULT_FRONTEND_URL,
) -> str:
    """Shortcut to build a submitEvidence signing URL."""
    return build_sign_url(
        "submitEvidence", market_id,
        direction=direction, ipfs_hash=ipfs_hash, summary=summary,
        source=source, frontend_url=frontend_url,
    )


def build_redeem_url(
    market_id: int,
    *,
    source: str = "PDX Agent",
    frontend_url: str = DEFAULT_FRONTEND_URL,
) -> str:
    """Shortcut to build a redeem signing URL."""
    return build_sign_url(
        "redeem", market_id,
        source=source, frontend_url=frontend_url,
    )
