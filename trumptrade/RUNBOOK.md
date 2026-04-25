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
Expected: `53 passed`.

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

## 7-pre. Manage prediction-market venues

```bash
# list registered venues (defined in config/markets.yaml)
python -m trumptrade.cli markets-list

# filter by topic (which categories the venue typically lists)
python -m trumptrade.cli markets-list --topic tariff_china

# filter by class
python -m trumptrade.cli markets-list --venue-class regulated_us
```

Add a venue: edit `config/markets.yaml`, declare metadata block, point
`factory:` to a `PredictionMarketClient` subclass. To add a long-tail venue
without writing a custom client, use `PMXTClient` (requires
`pip install pmxt` + Node.js):

```yaml
- name: limitless
  factory: trumptrade.markets:PMXTClient
  args:
    exchange: limitless
  metadata:
    venue_class: onchain_evm
    base_currency: USDC
    chain: base
    ...
```

## 7. Cross-market arbitrage scanner (Polymarket vs Kalshi)

```bash
pip install requests   # only HTTP dep needed for arb-scan

# rule-based matcher (free, fast)
python -m trumptrade.cli arb-scan --query "Trump tariff" --limit 25 --min-edge 0.01

# Claude-based semantic matcher (~$0.01 per pair, more accurate)
export ANTHROPIC_API_KEY=sk-ant-...
python -m trumptrade.cli arb-scan --query "Trump tariff" --use-llm --min-edge 0.005

# include estimated round-trip fees
python -m trumptrade.cli arb-scan --query "Fed rate cut June" --fee 0.02
```

What it does:
1. Search both venues with the same free-text query
2. Match Polymarket markets <-> Kalshi markets that look like the same event
   (rule-based Jaccard token overlap by default; Claude Haiku semantic match
   with `--use-llm`)
3. Pull YES/NO bid/ask quotes
4. For each match find the cheapest pair: long YES on one venue + long NO on
   the other. If `yes_ask_cheap + no_ask_expensive < 1.0 - fees - min_edge`,
   it's a lock; print sized trade plan.

Output gives you the EXACT trade pair to execute manually
(Polymarket needs wallet signing, not yet wired). For Kalshi-only directional
trades, plug `KALSHI_EMAIL` + `KALSHI_PASSWORD` and call `KalshiClient.login()`.

**Risks** — read before trading any of these:
- Resolution-source mismatch: Kalshi and Polymarket may resolve the "same"
  event using different rules. Always read both rule books before sizing.
- Liquidity: small markets show wide spreads; the displayed ask may not fill
  at size. Use `volume_24h` as a rough liquidity gate.
- Settlement timing: contracts on the two venues may settle on different
  dates; mark-to-market drawdown possible mid-trade.
- Polymarket execution requires an EIP-712 wallet signature (USDC on Polygon).
  Live Polymarket trading is intentionally NOT wired in this MVP.

## 8. Manage signal sources via YAML

The signal-source layer is pluggable. Edit `config/sources.yaml` to add or
remove sources at runtime:

```bash
# list everything currently registered
python -m trumptrade.cli sources-list

# point at a different manifest
python -m trumptrade.cli sources-list --config /path/to/my_sources.yaml
```

Each entry in the manifest MUST declare its metadata (domain, markets,
industries, cadence, auth, cost, reliability) so downstream code knows what
the signal covers. To add a new source:

1. Implement a `SignalSource` subclass (see `signals/federal_register.py`
   as a reference).
2. Add an entry to `config/sources.yaml` with `factory: my.module:MyClass`,
   `args:`, and the `metadata:` block.
3. `python -m trumptrade.cli sources-list` will pick it up.

## 8.5. Position monitoring + automatic close

```bash
# one-shot sweep over all open positions
python -m trumptrade.cli monitor --once --mode alert

# continuous loop, default 30s polling
python -m trumptrade.cli monitor --mode alert --interval 30

# paper mode: positions get marked closed when a rule fires; no real orders
python -m trumptrade.cli monitor --mode paper

# inspect current positions
python -m trumptrade.cli positions
python -m trumptrade.cli positions --show-closed

# manually close a position
python -m trumptrade.cli close-position <id> --exit-price 0.62
```

Six exit triggers run on every tick (priority order):

1. `walkback`         — Trump reversed in same category (≤48h)
2. `arb_convergence`  — locked spread closed → take profit early
3. `stop_loss`        — mark price hit `stop_loss_price`
4. `take_profit`      — mark price hit `take_profit_price`
5. `time_decay`       — market closes within N hours (default 24)
6. `liquidity_drop`   — 24h volume below threshold

Positions persist to `data/positions.jsonl`; close orders to
`data/close_orders.jsonl`. Both files are append-only logs.

Modes:
- `alert`  — log decision, do NOT submit. **Recommended for first 1-2 weeks.**
- `paper`  — log + mark position closed in store; no broker call
- `live`   — actually submit. Requires per-venue trader to implement
             `submit_close(order)`. Not wired by default.

## 8.6. Risk management

```bash
python -m trumptrade.cli risk-status
```

Edit caps in `config/risk_limits.yaml`:

| Limit | Default | Meaning |
|---|---|---|
| `account_value_usd` | 10000 | Sets denominator for all % caps |
| `max_total_exposure_pct` | 30% | Cap across all open positions |
| `max_per_venue_pct` | 15% | Per venue (Polymarket / Kalshi / ...) |
| `max_per_category_pct` | 10% | Per playbook category |
| `max_per_event_pct` | 5% | Per single event |
| `max_per_position_pct` | 3% | Single position |
| `daily_loss_circuit_breaker_pct` | 5% | Stop new opens after N% drawdown today |
| `max_open_positions` | 50 | Hard count cap |
| `min_market_volume_24h` | 1000 | Reject markets with thin liquidity |

`RiskChecker.check()` is called pre-trade by the orchestrator (when wired).
Returns a `RiskVerdict` with allowed=False + breach details if any cap fails.

## 8.65. Agents + Orders (decision/execution layer)

The full pipeline is now layered:

```
SIGNAL  ──► AGENT  ──► TradeDecision  ──► OrderRouter  ──► VenueExecutor  ──► Fill ──► Position
(sources/)   (agents/)                    (orders/)      (orders/)              (monitor/)
```

### Agents

Three concrete agents live in `trumptrade.agents`:

| Agent | Input | Output |
|---|---|---|
| `PolicyAgent`  | Trump-policy `Signal`         | `open` decisions on every venue carrying that policy category |
| `ArbAgent`     | Any signal (uses `signal.text`)| Two linked `open` decisions (long YES + long NO across venues) |
| `ExitAgent`    | Tick (no signal)              | `close` decisions for any open position triggering a rule |

Every agent emits `TradeDecision` objects with: action, venue, market, side,
size, price_limit, confidence, suggested_stop / take_profit / max_hold_until,
linked_decision_id (for arb pairs), target_position_id (for closes).

### OrderRouter

`OrderRouter.route(decisions)` does, per decision:

1. Build an `Order` from the decision
2. Pre-trade risk check (only for opens) via `RiskChecker`
3. Submit to the right venue executor
4. On fill, reconcile to `PositionStore` (insert for opens, mark-closed for closes)
5. For linked legs: if either leg rejects, cancel the partner best-effort

### Venue executors

`SimulatedExecutor` is the reference impl — fills instantly at limit price (or
quote-mid if a `quote_fn` is provided). For real venues, subclass
`VenueExecutor` and implement `submit()` + `cancel()`. Three concrete
executors are NOT yet wired (Kalshi REST, Polymarket EIP-712, Predict.fun
REST) — those are next.

### How this changes day-to-day usage

Most users don't touch agents/orders directly — the existing CLI commands
(`watch`, `monitor`, `arb-scan`) will be re-wired in a follow-up to use
`OrderRouter` instead of writing positions/closes directly. Right now the
agents+orders layer is exercised through unit tests; full pipeline wiring is
the next step.

### Markets-as-signals

`signals/market_signal.py` ships two market-side signal sources you can
register in `config/sources.yaml`:

- `PriceJumpSource` — emits a Signal when a watched market's mid moves
   ≥ N% between polls (good for fast-arb agents)
- `ArbOpportunitySource` — wraps `ArbScanner`; each detected arb becomes
   a Signal so `ArbAgent` can act on it

This closes the loop: market behaviour itself is a signal, classified and
routed the same way Trump posts are.

## 8.7. Dashboard (Streamlit)

```bash
pip install streamlit pandas
python -m trumptrade.cli dashboard       # opens http://localhost:8501
```

Five tabs:
- **positions** — open / closed, with unrealized + realized P&L
- **alerts** — recent classification alerts + bar chart by category
- **markets** — registered venues from `markets.yaml`
- **sources** — registered signal sources from `sources.yaml`
- **risk** — current exposure vs limits, daily P&L vs circuit breaker

## 9. Paper trade via Alpaca

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

## 10. Customize the playbook

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

## 11. File & data reference

| Path | What |
|---|---|
| `trumptrade/trumptrade/cli.py` | CLI entry (`watch`, `analyze`, `paper-trade`, `backtest`, `arb-scan`, `sources-list`) |
| `trumptrade/trumptrade/signals/registry.py` | `SourceRegistry`: register / unregister / query sources |
| `trumptrade/trumptrade/signals/metadata.py` | `SourceMetadata`: domain / markets / industries / cadence / auth / cost / reliability |
| `trumptrade/trumptrade/signals/federal_register.py` | Federal Register presidential-document poller |
| `trumptrade/trumptrade/markets/polymarket.py` | Polymarket Gamma + CLOB read-only client |
| `trumptrade/trumptrade/markets/kalshi.py` | Kalshi v2 REST read-only client (with optional JWT login) |
| `trumptrade/trumptrade/arb/matcher.py` | Match same event across venues (rules + LLM) |
| `trumptrade/trumptrade/arb/detector.py` | Compute cross-market lock from a matched pair |
| `trumptrade/trumptrade/arb/scanner.py` | End-to-end search → match → quote → opportunity |
| `trumptrade/config/sources.yaml` | Pluggable signal-source manifest |
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

## 12. Common pitfalls

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

## 13. What's not in this tool (yet)

- Truth Social real-time scraping — use RSS or paste posts into a JSON file
- Live-account trading (Alpaca live endpoint) — intentionally not wired
- Polymarket execution (EIP-712 wallet signing) — `arb-scan` outputs trade
  plans only; you sign and submit manually for now
- Kalshi order placement — login wired, order endpoints not yet exposed in CLI
- Prompt-cache 1-hour TTL (currently 5min default) — change in
  `policy_classifier.py` if running continuous watch loop
- TradingAgents deep analysis per ticker — separate integration task
- Sharpe / max DD calculation — backtest reports P&L / win rate only
- Backtest parallelization — runs serially over alerts
- Pipeline integration: trump signal classifier doesn't yet auto-trigger
  `arb-scan` for the matching policy category. Run them as separate steps
  for now.
