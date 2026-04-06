import hashlib
import json
import httpx
from app.config import settings


class IPFSService:
    """IPFS pinning via Pinata. Falls back to local mock if no API key."""

    def pin_json(self, data: dict) -> str:
        """Pin JSON data to IPFS, return CID."""
        if settings.pinata_api_key:
            return self._pinata_pin(data)
        return self._mock_pin(data)

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
        """Generate a deterministic fake CID for testing."""
        content = json.dumps(data, sort_keys=True).encode()
        h = hashlib.sha256(content).hexdigest()[:46]
        return f"Qm{h}"

    def data_to_bytes32(self, cid: str) -> bytes:
        """Convert CID string to bytes32 for on-chain storage."""
        return hashlib.sha256(cid.encode()).digest()


ipfs_service = IPFSService()
