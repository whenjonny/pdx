"""Streamlit dashboard for trumptrade. Run:

    pip install streamlit
    streamlit run trumptrade/dashboard/app.py

Reads from local jsonl + yaml, no backend service required.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    import streamlit as st
    import pandas as pd
except ImportError as e:
    raise SystemExit(
        "Dashboard requires streamlit + pandas: pip install streamlit pandas"
    ) from e

from trumptrade.config import load_playbook, data_dir
from trumptrade.monitor import PositionStore
from trumptrade.signals import SourceRegistry
from trumptrade.markets import VenueRegistry
from trumptrade.risk import load_risk_limits, RiskChecker

ROOT = Path(__file__).resolve().parent.parent.parent
CFG = ROOT / "config"
DATA = ROOT / "data"


# --------------------------------------------------------------------------
# data loaders
# --------------------------------------------------------------------------

@st.cache_data(ttl=15)
def load_alerts() -> pd.DataFrame:
    p = DATA / "alerts.jsonl"
    if not p.exists():
        return pd.DataFrame()
    rows = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    df = pd.json_normalize(rows)
    return df


@st.cache_data(ttl=15)
def load_positions() -> tuple[pd.DataFrame, pd.DataFrame]:
    store = PositionStore(DATA / "positions.jsonl")
    open_df = pd.DataFrame([p.model_dump() for p in store.open_positions()])
    closed_df = pd.DataFrame([p.model_dump() for p in store.closed_positions()])
    return open_df, closed_df


@st.cache_data(ttl=60)
def load_sources() -> pd.DataFrame:
    p = CFG / "sources.yaml"
    if not p.exists():
        return pd.DataFrame()
    try:
        r = SourceRegistry.from_yaml(p)
    except Exception as e:
        st.error(f"sources.yaml parse error: {e}")
        return pd.DataFrame()
    return pd.DataFrame([m.model_dump() for _, m in r.all()])


@st.cache_data(ttl=60)
def load_venues() -> pd.DataFrame:
    p = CFG / "markets.yaml"
    if not p.exists():
        return pd.DataFrame()
    try:
        r = VenueRegistry.from_yaml(p)
    except Exception as e:
        st.error(f"markets.yaml parse error: {e}")
        return pd.DataFrame()
    return pd.DataFrame([m.model_dump() for _, m in r.all()])


# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------

st.set_page_config(page_title="trumptrade", layout="wide")
st.title("trumptrade dashboard")
st.caption(f"loaded at {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

tab_pos, tab_decisions, tab_orders, tab_alerts, tab_markets, tab_sources, tab_risk, tab_report = st.tabs(
    ["positions", "decisions", "orders", "alerts", "markets", "sources", "risk", "report"]
)


# ---- positions tab --------------------------------------------------------
with tab_pos:
    open_df, closed_df = load_positions()

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("open positions", len(open_df))
    col2.metric("closed positions", len(closed_df))

    if not closed_df.empty and "realized_pnl" in closed_df.columns:
        wins = (closed_df["realized_pnl"] > 0).sum()
        losses = (closed_df["realized_pnl"] <= 0).sum()
        win_rate = wins / max(len(closed_df), 1)
        col3.metric("win rate", f"{win_rate:.1%}", delta=f"{wins}W / {losses}L")
        col4.metric("realized P&L ($)", f"{closed_df['realized_pnl'].sum():+,.2f}")

    if not open_df.empty:
        notional = (open_df["entry_price"] * open_df["size_contracts"]).sum()
        if "current_mark" in open_df.columns:
            unreal = ((open_df["current_mark"].fillna(open_df["entry_price"]) - open_df["entry_price"])
                      * open_df["size_contracts"]).sum()
        else:
            unreal = 0.0
        col5.metric("open + unreal", f"${notional:,.2f}", delta=f"u-pnl ${unreal:+,.2f}")

    st.subheader("open")
    if open_df.empty:
        st.info("no open positions")
    else:
        st.dataframe(
            open_df[[
                "id", "venue", "market_title", "side", "entry_price",
                "size_contracts", "current_mark", "stop_loss_price",
                "take_profit_price", "entry_at",
            ]],
            use_container_width=True,
        )

    st.subheader("closed (most recent 50)")
    if closed_df.empty:
        st.info("nothing closed yet")
    else:
        cd = closed_df.sort_values("closed_at", ascending=False).head(50)
        st.dataframe(
            cd[[
                "id", "venue", "market_title", "side",
                "entry_price", "exit_price", "realized_pnl",
                "exit_reason", "closed_at",
            ]],
            use_container_width=True,
        )


# ---- decisions tab --------------------------------------------------------
with tab_decisions:
    dec_path = DATA / "decisions.jsonl"
    if not dec_path.exists():
        st.info("no decisions yet — run `trumptrade trade-loop --once` to seed.")
    else:
        rows = []
        for line in dec_path.read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
        if not rows:
            st.info("no decisions logged")
        else:
            df = pd.DataFrame(rows)
            colA, colB, colC = st.columns(3)
            colA.metric("total decisions", len(df))
            if "agent_name" in df.columns:
                top_agent = df["agent_name"].value_counts().idxmax()
                colB.metric("top agent", top_agent)
            if "action" in df.columns:
                opens = (df["action"] == "open").sum()
                closes = (df["action"] == "close").sum()
                colC.metric("open / close", f"{opens} / {closes}")
            st.dataframe(
                df[["created_at", "agent_name", "action", "venue", "side",
                    "size_contracts", "confidence", "market_title"]].tail(100),
                use_container_width=True,
            )
            if "agent_name" in df.columns:
                st.subheader("decisions by agent")
                st.bar_chart(df["agent_name"].value_counts())


# ---- orders tab -----------------------------------------------------------
with tab_orders:
    ord_path = DATA / "orders.jsonl"
    if not ord_path.exists():
        st.info("no orders yet")
    else:
        # latest entry per id wins
        by_id: dict = {}
        for line in ord_path.read_text().splitlines():
            if line.strip():
                try:
                    o = json.loads(line)
                    by_id[o["id"]] = o
                except Exception:
                    pass
        if not by_id:
            st.info("no orders")
        else:
            df = pd.DataFrame(list(by_id.values()))
            colA, colB, colC, colD = st.columns(4)
            colA.metric("total orders", len(df))
            if "status" in df.columns:
                fill_count = ((df["status"] == "filled") | (df["status"] == "partially_filled")).sum()
                colB.metric("filled", fill_count)
                rej_count = (df["status"] == "rejected").sum()
                colC.metric("rejected", rej_count)
                err_count = (df["status"] == "error").sum()
                colD.metric("errors", err_count)
            st.dataframe(
                df[["created_at", "venue", "side", "qty_contracts", "limit_price",
                    "status", "agent_name", "market_title", "error"]].tail(100),
                use_container_width=True,
            )
            if "status" in df.columns:
                st.subheader("orders by status")
                st.bar_chart(df["status"].value_counts())


# ---- alerts tab -----------------------------------------------------------
with tab_alerts:
    df = load_alerts()
    if df.empty:
        st.info("no alerts. run `trumptrade watch --source mock --once --fake`.")
    else:
        st.dataframe(df.tail(50), use_container_width=True)
        st.subheader("alert frequency by category")
        if "classification.category" in df.columns:
            counts = df["classification.category"].value_counts()
            st.bar_chart(counts)


# ---- markets tab ----------------------------------------------------------
with tab_markets:
    venues = load_venues()
    if venues.empty:
        st.info("no venues registered. edit `config/markets.yaml`.")
    else:
        st.dataframe(venues, use_container_width=True)


# ---- sources tab ----------------------------------------------------------
with tab_sources:
    src = load_sources()
    if src.empty:
        st.info("no signal sources registered. edit `config/sources.yaml`.")
    else:
        st.dataframe(src, use_container_width=True)


# ---- report tab -----------------------------------------------------------
with tab_report:
    from trumptrade.reports import build_summary
    try:
        summary = build_summary(DATA)
    except Exception as e:
        st.error(f"report error: {e}")
    else:
        st.subheader("headline numbers")
        m = st.columns(4)
        m[0].metric("signals", summary.n_signals)
        m[1].metric("decisions", summary.n_decisions)
        m[2].metric("orders", summary.n_orders, delta=f"fill {summary.fill_rate:.0%}")
        m[3].metric("win rate", f"{summary.win_rate:.1%}",
                    delta=f"{summary.n_winning}W / {summary.n_losing}L")
        m2 = st.columns(3)
        m2[0].metric("realized P&L", f"${summary.realized_pnl:+,.2f}")
        m2[1].metric("unrealized P&L", f"${summary.unrealized_pnl:+,.2f}")
        m2[2].metric("avg win / avg loss",
                     f"${summary.avg_win:+,.2f} / ${summary.avg_loss:+,.2f}")

        if summary.window_start and summary.window_end:
            st.caption(f"signal window: {summary.window_start.isoformat(timespec='minutes')} "
                       f"-> {summary.window_end.isoformat(timespec='minutes')}")
        st.code(summary.render_text())


# ---- risk tab -------------------------------------------------------------
with tab_risk:
    risk_path = CFG / "risk_limits.yaml"
    try:
        limits = load_risk_limits(risk_path if risk_path.exists() else None)
    except Exception as e:
        st.error(f"risk_limits.yaml parse error: {e}")
        limits = None

    if limits:
        store = PositionStore(DATA / "positions.jsonl")
        st.subheader("limits")
        st.dataframe(pd.DataFrame([limits.model_dump()]).T.rename(columns={0: "value"}),
                     use_container_width=True)

        st.subheader("current usage")
        opens = store.open_positions()
        total_notional = sum(p.notional_at_entry for p in opens)
        st.metric("total exposure",
                  f"${total_notional:,.2f} / ${limits.max_total_exposure_pct * limits.account_value_usd:,.2f}",
                  delta=f"{(total_notional / limits.account_value_usd):.1%} of acct")

        per_venue = {}
        for p in opens:
            per_venue.setdefault(p.venue, 0.0)
            per_venue[p.venue] += p.notional_at_entry
        if per_venue:
            df_v = pd.DataFrame(
                [{"venue": k, "notional": v,
                  "pct_of_acct": v / limits.account_value_usd}
                 for k, v in per_venue.items()]
            )
            st.dataframe(df_v, use_container_width=True)

        st.subheader("daily realized P&L")
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_pnl = sum((p.realized_pnl or 0.0) for p in store.closed_positions()
                        if p.closed_at and p.closed_at >= today)
        circuit = -limits.daily_loss_circuit_breaker_pct * limits.account_value_usd
        st.metric("today realized", f"${today_pnl:+,.2f}",
                  delta=f"circuit breaker at ${circuit:.2f}")
