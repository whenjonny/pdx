"""Domain-based credibility scoring for evidence sources.

Maps known domains to credibility scores (1-10 scale).
Unknown domains receive a conservative baseline score.
"""

from urllib.parse import urlparse

DOMAIN_SCORES: dict[str, float] = {
    # Major news agencies
    "reuters.com": 9.0,
    "apnews.com": 9.0,
    "bbc.com": 8.5,
    "bbc.co.uk": 8.5,
    # Financial / crypto
    "bloomberg.com": 8.5,
    "ft.com": 8.5,
    "wsj.com": 8.5,
    "coindesk.com": 7.5,
    "theblock.co": 7.5,
    "cointelegraph.com": 7.0,
    "decrypt.co": 7.0,
    # Academic / technical
    "arxiv.org": 8.0,
    "nature.com": 9.0,
    "science.org": 9.0,
    "github.com": 7.0,
    # Government / institutional
    "sec.gov": 9.0,
    "federalreserve.gov": 9.0,
    "imf.org": 8.5,
    "worldbank.org": 8.5,
    # Data providers
    "coingecko.com": 7.0,
    "defillama.com": 7.0,
    "dune.com": 7.0,
    "etherscan.io": 7.5,
    "basescan.org": 7.5,
}

DEFAULT_SCORE = 3.0


def score_domain(url: str) -> float:
    """Return credibility score for a URL's domain. Falls back to DEFAULT_SCORE."""
    try:
        host = urlparse(url).hostname or ""
        # Strip www. prefix
        if host.startswith("www."):
            host = host[4:]
        # Check exact match, then parent domain
        if host in DOMAIN_SCORES:
            return DOMAIN_SCORES[host]
        parts = host.split(".")
        if len(parts) > 2:
            parent = ".".join(parts[-2:])
            if parent in DOMAIN_SCORES:
                return DOMAIN_SCORES[parent]
    except Exception:
        pass
    return DEFAULT_SCORE
