# trumptrade — Runbook

Step-by-step guide to running every mode of the tool.

---

## 0. Install (one-time)

```bash
cd /home/user/pdx/trumptrade
pip install -e .
```

Optional extras depending on what you want to run:

| Feature | Extra install | Env var |
|---|---|---|
| Real LLM classifier | — (anthropic already in deps) | `ANTHROPIC_API_KEY=sk-ant-...` |
| RSS feed source | `pip install feedparser` | — |
| Real historical prices | `pip install yfinance` | — |
| Live Alpaca paper trade | `pip install alpaca-py` | `ALPACA_API_KEY`, `ALPACA_SECRET` |
| Truth Social scrape | `pip install truthbrush` (third-party, ToS risk) | — |

Nothing else is required for the offline demo flow below.

---

## 1. Self-test (no API key, no network)

```bash
cd /home/user/pdx/trumptrade
python -m pytest -v
```
Expected: `15 passed`.

---

## 2. Demo end-to-end (no API key)

Three commands, each depends only on the previous artefact:

```bash
# 2a. Classify 20 sample Trump posts -> write data/alerts.jsonl
python -m trumptrade.cli watch --source mock --once --fake

# 2b. Turn the latest alert into a simulated order report
python -m trumptrade.cli paper-trade --mode sim --price-source stub

# 2c. Replay all alerts through a simulated paper trader + compute P&L
python -m trumptrade.cli backtest --price-source stub --hold-days 3
```

`--fake` uses the keyword-based classifier so no Claude API call is made.

---

## 3. Single-post analysis (ad hoc)

```bash
# fake classifier (offline)
python -m trumptrade.cli analyze --fake \
  "Effective May 1st, a new 35% tariff on Chinese EVs"

# real Claude classifier (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
python -m trumptrade.cli analyze \
  "Effective May 1st, a new 35% tariff on Chinese EVs"
```

---

## 4. Watch a real RSS feed

```bash
pip install feedparser
python -m trumptrade.cli watch --source rss \
    --url https://www.whitehouse.gov/feed/ \
    --interval 60
```
Ctrl-C to stop. Alerts append to `data/alerts.jsonl`.

Useful feeds to try:
- `https://www.whitehouse.gov/feed/` — WH press releases
- USTR tariff announcements (if publicly syndicated)
- Any aggregator that republishes Trump posts via RSS

---

## 5. Real Claude classification

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m trumptrade.cli watch --source mock --once
```
Omit `--fake` to use Claude Opus 4.7. Prompt caching is enabled — the 3.2KB
playbook system prompt is written to cache on the first call
(`cache_creation_input_tokens` > 0), then read on each subsequent call
(`cache_read_input_tokens` > 0). You can verify via debug logs:

```bash
python -m trumptrade.cli -v watch --source mock --once
# grep for: "classifier usage: input=... cache_read=..."
```

Estimated cost: ~$0.01-0.05 per post (depends on adaptive thinking depth).

---

## 6. Backtest with real prices

```bash
pip install yfinance
python -m trumptrade.cli backtest \
    --alerts data/alerts.jsonl \
    --price-source yfinance \
    --capital 100000 \
    --hold-days 5
```

To test the walk-back close logic, add a signal that reverses an earlier
policy (same category, opposite sentiment) within 48h to your input, re-run
`watch`, then re-run `backtest`. Closes will show `[walk_back]` reason.

To disable walk-back and hold everything to `--hold-days`:
```bash
python -m trumptrade.cli backtest --no-walkback
```

---

## 7. Paper trade via Alpaca

**Read the Alpaca paper-account setup first. Never run this against a live
account until you've validated the flow.**

```bash
pip install alpaca-py
export ALPACA_API_KEY=PKxxx...
export ALPACA_SECRET=...

# trades the LATEST alert from data/alerts.jsonl
python -m trumptrade.cli paper-trade --mode alpaca --price-source yfinance

# or pick a specific alert by signal id
python -m trumptrade.cli paper-trade --mode alpaca \
    --alert-id sample-02 --price-source yfinance
```

Before any order is sent, `size_basket()` applies the playbook risk gates:

| Gate | Default |
|---|---|
| `max_basket_notional_pct` | 10% of account |
| `max_single_ticker_notional_pct` | 3% of account |
| `mandatory_stop_loss_pct` | 8% |
| Risk per trade | 1% of account |

Change any of these in `config/trump_policy_playbook.yaml`.

---

## 8. Customize the playbook

Edit `config/trump_policy_playbook.yaml` to:
- Add a new policy category with its own ticker basket
- Adjust ticker weights per category
- Change follow-through priors (probability an announcement becomes policy)
- Tighten / loosen risk gates

No code changes needed — restart `watch` to pick up the new YAML.

Point to an alternate playbook via env:
```bash
export TRUMPTRADE_PLAYBOOK=/path/to/my_custom.yaml
```

---

## 9. File & data reference

| Path | What |
|---|---|
| `trumptrade/trumptrade/cli.py` | CLI entry (`watch`, `analyze`, `paper-trade`, `backtest`) |
| `trumptrade/trumptrade/classifier/policy_classifier.py` | Claude Opus 4.7 classifier + prompt-caching |
| `trumptrade/trumptrade/classifier/fake_classifier.py` | Offline keyword classifier (no API key) |
| `trumptrade/trumptrade/signals/` | `MockFileSource`, `RSSFeedSource`, Truth Social stub |
| `trumptrade/trumptrade/execution/basket.py` | Playbook lookup: classification -> basket legs |
| `trumptrade/trumptrade/execution/position_sizer.py` | Risk-based share count |
| `trumptrade/trumptrade/execution/walkback.py` | Detects 48h policy reversals |
| `trumptrade/trumptrade/execution/paper_trader.py` | `SimulatedPaperTrader`, `AlpacaPaperTrader` |
| `trumptrade/trumptrade/backtest/` | Offline backtest harness + price sources |
| `trumptrade/config/trump_policy_playbook.yaml` | 9 categories × ticker baskets |
| `trumptrade/data/sample_posts/posts.json` | 20 demo posts spanning all 9 categories |
| `trumptrade/data/alerts.jsonl` | Append-only alert log (generated) |

---

## 10. Common pitfalls

- **`watch` emits 0 alerts:** likely your confidence threshold in
  `playbook.risk_gates.min_confidence_to_alert` is too high, or the fake
  classifier's keyword match rate is too low for your input corpus. Run with
  `-v` for per-signal reasons.
- **`paper-trade` reports 0 orders:** the latest alert may be `dovish` or
  `unknown` with no basket. Pick a specific hawkish alert via `--alert-id`.
- **`backtest` all trades show $0 P&L:** you're using `StubPriceSource` which
  is deterministic and smooth. Switch to `--price-source yfinance` for real data.
- **Prompt cache not hitting:** run with `-v` and inspect
  `cache_read_input_tokens` on the second call. If it stays 0, the system
  prompt isn't byte-stable — but the tests (`test_system_prompt_deterministic`)
  verify this. If you edit the playbook, the first call after the edit will
  rebuild the cache.
- **Alpaca paper submit fails:** `ALPACA_API_KEY`/`SECRET` must be for the paper
  endpoint (key prefix `PK`, not `AK`). The SDK defaults to live otherwise.

---

## 11. What's not in this tool (yet)

- Truth Social real-time scraping — use RSS or paste posts into a JSON file
- Live-account trading (Alpaca live endpoint) — intentionally not wired
- Prompt-cache 1-hour TTL (currently 5min default) — change in
  `policy_classifier.py` if running continuous watch loop
- TradingAgents deep analysis per ticker — separate integration task
- Sharpe / max DD calculation — backtest reports P&L / win rate only
- Backtest parallelization — runs serially over alerts
