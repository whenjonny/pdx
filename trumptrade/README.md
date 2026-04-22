# trumptrade

Week 1 MVP: read-only Trump-policy signal monitor. Watches a signal source
(mock file / RSS / Truth Social stub), classifies each post with Claude, maps
the classification to a ticker basket via a YAML playbook, and emits an alert.

**No order execution.** Week 1 is for evaluating signal accuracy.

## Layout

```
trumptrade/
  config/
    trump_policy_playbook.yaml   # 9 policy categories -> ticker baskets
  trumptrade/
    signals/        (MockFileSource, RSSFeedSource, TruthSocialSource stub)
    classifier/     (Claude Opus 4.7, prompt-cached playbook)
    execution/      (basket expander + alerter; persists to alerts.jsonl)
    pipeline.py     (orchestrator)
    cli.py          (trumptrade watch / analyze)
  data/sample_posts/posts.json   # 5 demo posts
  tests/
  examples/
```

## Install

```bash
cd trumptrade
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
```

## Quick start

```bash
# one-shot analysis of arbitrary text
trumptrade analyze "Effective May 1st, a new 35% tariff on Chinese EVs"

# watch sample posts (one pass, no loop)
trumptrade watch --source mock --once

# continuous loop
trumptrade watch --source mock --interval 30

# RSS feed
trumptrade watch --source rss --url https://example.com/whitehouse.rss
```

## Run tests

```bash
pip install pytest
pytest -v tests/test_basket.py tests/test_classifier_prompt.py  # no API key needed
pytest -v tests/                                                # all (e2e uses fake classifier)
```

## Config

| Env var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — (required) | Claude API key |
| `TRUMPTRADE_PLAYBOOK` | `config/trump_policy_playbook.yaml` | Playbook override |
| `TRUMPTRADE_DATA_DIR` | `./data/` | Where `alerts.jsonl` lands |

## How the classifier works

`policy_classifier.py` renders the playbook into a **deterministic** system
prompt (sorted keys, byte-stable) and marks it with `cache_control:
{"type": "ephemeral"}`. First call writes the cache (~1.25x); every subsequent
call reads it (~0.1x). The volatile part (the signal text) is the user prompt.

Response format is constrained via `output_config.format` with a JSON schema,
so the classifier output is parse-safe.

Model defaults:
- `claude-opus-4-7`
- `thinking: {type: "adaptive"}`
- `output_config.effort: "high"`

## Playbook

`config/trump_policy_playbook.yaml` defines 9 categories:
`tariff_china`, `energy_oil_gas`, `crypto_friendly`, `defense_spending`,
`bank_deregulation`, `pharma_price_pressure`, `immigration_border`,
`big_tech_antitrust`, `clean_energy_rollback`.

Each has `hawkish_long` / `hawkish_short` / `dovish_long` / `dovish_short`
ticker lists. Editing the YAML is the primary way to tune this tool.

## What's NOT in Week 1
- Paper or live trading (no broker integration)
- Truth Social scraping (stubbed)
- TradingAgents deep per-ticker analysis
- Walk-back detection (reverse positions if Trump flip-flops)
- Backtest harness

See `.trellis/tasks/04-trumptrade/SPEC.md` for the roadmap.
