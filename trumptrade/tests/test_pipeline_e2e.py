from datetime import datetime, timezone
from pathlib import Path
from trumptrade.pipeline import Pipeline
from trumptrade.signals import MockFileSource
from trumptrade.types import Signal, Classification
from trumptrade.execution import Alerter


def fake_classifier(signal: Signal, playbook: dict) -> Classification:
    # High-confidence tariff signal for any text containing "tariff"
    if "tariff" in signal.text.lower():
        return Classification(
            category="tariff_china",
            sentiment="hawkish",
            follow_through=0.7,
            rationale="mentioned tariffs on china",
            confidence=0.9,
            original_excerpt=signal.text[:120],
        )
    return Classification(
        category="unknown",
        sentiment="neutral",
        follow_through=0.0,
        rationale="off-topic",
        confidence=0.0,
        original_excerpt=signal.text[:120],
    )


def test_pipeline_processes_sample_posts(tmp_path):
    posts = [
        {
            "id": "t1",
            "author": "realDonaldTrump",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "text": "New 50% tariff on Chinese EVs effective next month",
            "source": "test",
        },
        {
            "id": "t2",
            "author": "realDonaldTrump",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "text": "Beautiful weather at Mar-a-Lago today",
            "source": "test",
        },
    ]
    posts_path = tmp_path / "posts.json"
    import json
    posts_path.write_text(json.dumps(posts))

    log_path = tmp_path / "alerts.jsonl"
    alerter = Alerter(min_confidence=0.5, log_path=log_path)

    playbook = {
        "categories": {
            "tariff_china": {
                "hawkish_long": [{"ticker": "NUE", "weight": 0.9, "thesis": "steel"}],
                "hawkish_short": [{"ticker": "FXI", "weight": 0.85, "thesis": "china"}],
            }
        }
    }

    pipe = Pipeline(
        source=MockFileSource(posts_path),
        playbook=playbook,
        alerter=alerter,
        classify_fn=fake_classifier,
    )

    emitted = pipe.run_once()
    assert emitted == 1
    # Second run: no new signals (mock source dedups by id)
    assert pipe.run_once() == 0
    assert log_path.exists()
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert "tariff_china" in lines[0]
    assert "NUE" in lines[0]
