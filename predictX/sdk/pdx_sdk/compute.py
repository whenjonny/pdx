"""Local compute tasks: embeddings and Monte Carlo simulation."""

from __future__ import annotations

import logging
import warnings
from typing import Optional

import numpy as np

from pdx_sdk.types import MonteCarloResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

_model = None  # lazily loaded sentence-transformer


def compute_embedding(text: str) -> list[float]:
    """Compute a 384-dimensional embedding for *text*.

    Attempts to use ``sentence-transformers`` with the
    ``all-MiniLM-L6-v2`` model.  If the library is not installed a
    random 384-dim vector is returned with a warning.
    """
    global _model

    try:
        from sentence_transformers import SentenceTransformer

        if _model is None:
            logger.info("Loading sentence-transformers model (all-MiniLM-L6-v2)...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")

        embedding = _model.encode(text, show_progress_bar=False)
        return embedding.tolist()

    except ImportError:
        warnings.warn(
            "sentence-transformers not installed; returning a random 384-dim vector. "
            "Install with: pip install sentence-transformers",
            stacklevel=2,
        )
        rng = np.random.default_rng()
        vec = rng.standard_normal(384)
        # L2-normalise so it behaves like a real embedding
        vec = vec / np.linalg.norm(vec)
        return vec.tolist()


# ---------------------------------------------------------------------------
# Monte Carlo simulation
# ---------------------------------------------------------------------------


def run_monte_carlo(
    prior_yes: float,
    evidence_scores: Optional[list[float]] = None,
    weights: Optional[list[float]] = None,
    n_sim: int = 5_000,
) -> MonteCarloResult:
    """Run a Monte Carlo simulation to estimate outcome probability.

    Parameters
    ----------
    prior_yes : float
        Prior probability of YES outcome, in ``[0, 1]``.
    evidence_scores : list[float] | None
        Scores from evidence analysis, each in ``[-1, 1]`` where positive
        values support YES.
    weights : list[float] | None
        Importance weights for each evidence score.  Defaults to uniform.
    n_sim : int
        Number of simulation runs (default 5000).

    Returns
    -------
    MonteCarloResult
        Aggregated statistics from the simulation.
    """
    rng = np.random.default_rng()

    if evidence_scores is None or len(evidence_scores) == 0:
        # No evidence -- sample directly from a Beta centred on prior
        alpha = max(prior_yes * 10, 0.1)
        beta_param = max((1 - prior_yes) * 10, 0.1)
        samples = rng.beta(alpha, beta_param, size=n_sim)
    else:
        scores = np.array(evidence_scores, dtype=float)
        if weights is None:
            w = np.ones_like(scores)
        else:
            w = np.array(weights, dtype=float)
        w = w / w.sum()  # normalise

        samples = np.empty(n_sim)
        for i in range(n_sim):
            # Bootstrap: sample evidence indices with replacement
            idx = rng.choice(len(scores), size=len(scores), replace=True)
            weighted_shift = np.sum(scores[idx] * w[idx])
            # Clamp adjusted probability to [0, 1]
            noise = rng.normal(0, 0.05)
            p = np.clip(prior_yes + weighted_shift * 0.5 + noise, 0.0, 1.0)
            samples[i] = p

    mean = float(np.mean(samples))
    std = float(np.std(samples))
    sorted_samples = np.sort(samples)
    ci_lower = float(sorted_samples[int(0.025 * n_sim)])
    ci_upper = float(sorted_samples[int(0.975 * n_sim)])

    return MonteCarloResult(
        mean=mean,
        std=std,
        ci_95_lower=ci_lower,
        ci_95_upper=ci_upper,
        n_simulations=n_sim,
    )
