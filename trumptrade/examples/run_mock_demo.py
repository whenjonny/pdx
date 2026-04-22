"""End-to-end demo using the mock signal source and real Anthropic classifier.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/run_mock_demo.py
"""
from __future__ import annotations
from pathlib import Path
from trumptrade.pipeline import Pipeline
from trumptrade.signals import MockFileSource

if __name__ == "__main__":
    here = Path(__file__).resolve().parent.parent
    posts = here / "data" / "sample_posts" / "posts.json"
    pipe = Pipeline(source=MockFileSource(posts))
    pipe.run_once()
