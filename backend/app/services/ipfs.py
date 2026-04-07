import hashlib
import json
import logging

import httpx
from app.config import settings

logger = logging.getLogger("ipfs")


class IPFSService:
    """IPFS pinning & fetching via Pinata. Falls back to local mock if no API key."""

    def __init__(self):
        # bytes32_hex -> CID mapping (populated on upload)
        self._cid_registry: dict[str, str] = {}
        # Mock mode: CID -> data (for local fetch without real IPFS)
        self._mock_store: dict[str, dict] = {}

    def pin_json(self, data: dict) -> str:
        """Pin JSON data to IPFS, return CID."""
        if settings.pinata_api_key:
            cid = self._pinata_pin(data)
        else:
            cid = self._mock_pin(data)

        # Register CID mapping for later retrieval
        bytes32_hex = "0x" + self.data_to_bytes32(cid).hex()
        self._cid_registry[bytes32_hex] = cid
        return cid

    def fetch_json(self, cid: str) -> dict | None:
        """Fetch JSON content from IPFS by CID."""
        # Check mock store first
        if cid in self._mock_store:
            return self._mock_store[cid]

        # Try Pinata dedicated gateway
        if settings.pinata_api_key:
            try:
                resp = httpx.get(
                    f"https://gateway.pinata.cloud/ipfs/{cid}",
                    headers={"pinata_api_key": settings.pinata_api_key},
                    timeout=15,
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                logger.warning("Pinata gateway fetch failed for %s: %s", cid, e)

        # Fallback to public IPFS gateway
        for gateway in ["https://ipfs.io/ipfs", "https://dweb.link/ipfs"]:
            try:
                resp = httpx.get(f"{gateway}/{cid}", timeout=15)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue

        logger.warning("Could not fetch IPFS content for CID %s", cid)
        return None

    def fetch_by_hash(self, bytes32_hex: str) -> dict | None:
        """Fetch IPFS content using on-chain bytes32 hash."""
        cid = self._cid_registry.get(bytes32_hex)
        if not cid:
            logger.debug("No CID registered for hash %s", bytes32_hex)
            return None
        return self.fetch_json(cid)

    def get_cid(self, bytes32_hex: str) -> str | None:
        """Look up CID from bytes32 hash."""
        return self._cid_registry.get(bytes32_hex)

    def _pinata_pin(self, data: dict) -> str:
        resp = httpx.post(
            "https://api.pinata.cloud/pinning/pinJSONToIPFS",
            headers={
                "pinata_api_key": settings.pinata_api_key,
                "pinata_secret_api_key": settings.pinata_secret_key,
            },
            json={"pinataContent": data},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["IpfsHash"]

    def _mock_pin(self, data: dict) -> str:
        """Generate a deterministic fake CID for testing and store data."""
        content = json.dumps(data, sort_keys=True).encode()
        h = hashlib.sha256(content).hexdigest()[:46]
        cid = f"Qm{h}"
        self._mock_store[cid] = data
        return cid

    def data_to_bytes32(self, cid: str) -> bytes:
        """Convert CID string to bytes32 for on-chain storage."""
        return hashlib.sha256(cid.encode()).digest()


ipfs_service = IPFSService()
