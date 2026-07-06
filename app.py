from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import SignalEngine


ROOT = Path(__file__).parent
APP_STATE_VERSION = 7


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


st.set_page_config(page_title="Options Signal Desk", page_icon="📈", layout="wide")

# Streamlit preserves Python objects across hot reloads. Clear results created by an
# older Candidate schema before the UI attempts to read newly added fields.
saved_candidates = st.session_state.get("candidates", [])
candidate_schema_is_current = all(
    hasattr(candidate, field)
    for candidate in saved_candidates
    for field in ("setup_status", "checklist", "darvas", "company", "catalyst", "setup_type", "a_plus_score", "reversal_watch", "extended_watch")
)
if (
    st.session_state.get("app_state_version") != APP_STATE_VERSION
    or not candidate_schema_is_current
):
    for key in ("candidates", "errors", "scan_time"):
        st.session_state.pop(key, None)
    st.session_state["app_state_version"] = APP_STATE_VERSION

st.title("Options Signal Desk")
st.caption("Dylan Playbook V2: Market → theme → story → catalyst → stage → leadership → structure → confirmation → option → risk.")
st.caption("Only TRADE SETUP names have passed the live, liquid, affordable contract gate; WATCH names may appear before a contract qualifies.")
st.caption("PUT/CALL REVERSAL WATCH means the prior move is stretched; it is not an entry until the underlying confirms a reversal through structure and volume.")
st.caption("EXTENDED WATCH means momentum remains intact but chasing is blocked until a new base, hold, or retest forms.")
st.caption("Balanced radar: up to 3 CALL names and 3 PUT names. The app never changes direction merely to fill a quota.")

config = load_config()
with st.sidebar:
    st.header("Risk controls")
    account = st.number_input("Account size ($)", 100, 100000, int(config["account_size"]), 50)
    risk_pct = st.slider("Maximum premium risk per trade", 1, 20, int(config["max_risk_per_trade_pct"]), 1)
    minimum_confidence = st.slider("Minimum model confidence", 50, 75, int(config["minimum_confidence"]), 1)
    automatic_discovery = st.toggle("Automatic market discovery", value=bool(config.get("automatic_discovery", True)))
    discovery_limit = st.slider("Stocks sent to full news analysis", 10, 30, int(config.get("discovery_limit", 20)), 5)
    st.caption(
        f"Discovery keeps {len(config.get('discovery_universe', []))} core symbols and adds the live top "
        f"{config.get('top_market_universe_size', 0):,} U.S.-listed stocks, then fully analyzes the strongest movers."
    )
    st.caption("A second news lane adds fresh earnings, FDA, guidance, contract, acquisition, partnership and analyst-action names before ranking.")
    watchlist = st.text_area("Watchlist", ", ".join(config["watchlist"]))
    st.warning("A $500 account should not target fixed daily income. One long option can lose its entire premium.")

config["account_size"] = account
config["max_risk_per_trade_pct"] = risk_pct
config["minimum_confidence"] = minimum_confidence
config["automatic_discovery"] = automatic_discovery
config["discovery_limit"] = discovery_limit
config["watchlist"] = [s.strip().upper() for s in watchlist.split(",") if s.strip()]

if st.button("Run market scan", type="primary", use_container_width=True):
    with st.spinner("Reading prices, options chains, earnings and recent headlines…"):
        engine = SignalEngine(config)
        candidates, errors = engine.scan()
        st.session_state["candidates"] = candidates
        st.session_state["errors"] = errors
        st.session_state["scan_time"] = datetime.now().astimezone().strftime("%Y-%m-%d %I:%M:%S %p %Z")

if "candidates" not in st.session_state:
    st.info("Press **Run market scan**. The model may return no trade when signals are weak or contracts exceed your risk cap.")
    st.stop()

st.caption(f"Last scan: {st.session_state['scan_time']}. Quotes may be delayed; confirm every price in Robinhood.")
candidates = st.session_state["candidates"]
if not candidates:
    st.error("No candidate passed the evidence and risk filters. No trade is a valid result.")
else:
    call_count = sum(c.direction == "CALL" for c in candidates)
    put_count = sum(c.direction == "PUT" for c in candidates)
    call_metric, put_metric = st.columns(2)
    call_metric.metric("CALL radar", f"{call_count}/3")
    put_metric.metric("PUT radar", f"{put_count}/3")
    summary = pd.DataFrame([{
        "Symbol": c.symbol,
        "Status": c.setup_status,
        "Direction": c.direction,
        "Approved setup": c.setup_type,
        "A+ score": f"{c.a_plus_score}/100",
        "Confidence*": f"{c.confidence}%",
        "Stock price": f"${c.price:.2f}",
        "Affordable contract": c.option["contract"] if c.option else "None found",
        "Premium / max loss": f"${c.option['estimated_cost_and_max_loss']:.2f}" if c.option else "—",
        "Earnings": c.earnings,
    } for c in candidates])
    st.dataframe(summary, hide_index=True, use_container_width=True)
    st.caption("*Confidence is a heuristic evidence score, not the historical win probability or a promise of profit.")

    for rank, c in enumerate(candidates, 1):
        with st.expander(f"#{rank} {c.symbol} — {c.setup_status} — {c.direction} — {c.a_plus_score}/100", expanded=rank == 1):
            left, right = st.columns([3, 2])
            with left:
                st.subheader("Story + catalyst")
                st.write(f"**{c.company['name']}** — {c.company['sector']} / {c.company['industry']}")
                st.write(c.company["business"] or "Business summary unavailable; STORY rule fails.")
                st.write(f"**Detected catalyst:** {c.catalyst}")
                fundamentals = {
                    "Revenue growth": c.company["revenue_growth"],
                    "Earnings growth": c.company["earnings_growth"],
                    "Debt/equity": c.company["debt_to_equity"],
                }
                st.json(fundamentals)
                st.subheader("Why the model chose the direction")
                st.write(c.thesis)
                st.markdown("**Supporting evidence**")
                for item in c.catalysts or ["No additional catalyst passed the filter."]:
                    st.write(f"• {item}")
                st.markdown("**Trade framework**")
                st.write(c.entry_idea)
                st.write(c.invalidation)
                st.write(c.target_idea)
                st.markdown("**Risks**")
                for item in c.risks:
                    st.write(f"• {item}")
            with right:
                score = sum(c.checklist.values())
                st.metric("Playbook A+ score", f"{c.a_plus_score}/100", c.setup_status)
                st.write(f"**{c.setup_type}**")
                st.write(f"**Weinstein:** {c.weinstein_stage}")
                st.write(f"**Market:** {c.market_context}")
                st.markdown("**100-point decision sheet (10 points each)**")
                for rule, passed in c.checklist.items():
                    st.write(f"{'✅' if passed else '❌'} {rule}")
                st.markdown("**Darvas confirmation**")
                st.json(c.darvas)
                st.subheader("Signal composition")
                chart = go.Figure(go.Bar(
                    x=list(c.signal_details.values()),
                    y=list(c.signal_details.keys()),
                    orientation="h",
                    marker_color=["#22c55e" if v > 0 else "#ef4444" for v in c.signal_details.values()],
                ))
                chart.add_vline(x=0, line_width=1, line_color="white")
                chart.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(chart, use_container_width=True)
                st.metric("Next earnings date", c.earnings)
            st.subheader("Candidate contract")
            if c.option:
                st.json(c.option)
                st.warning("Use a limit order. Recheck bid/ask, liquidity, news and the underlying chart immediately before entry.")
            else:
                st.info("No sufficiently liquid near-the-money contract fit the configured premium-risk limit. Do not stretch the risk cap.")
            st.subheader("Recent headlines")
            for headline in c.headlines[:6]:
                mood = "positive" if headline["sentiment"] > .1 else "negative" if headline["sentiment"] < -.1 else "neutral"
                st.markdown(f"- [{headline['title']}]({headline['link']}) — {mood}")

errors = st.session_state.get("errors", [])
if errors:
    with st.expander("Data-source warnings"):
        st.write("\n".join(errors))

st.divider()
st.caption("Decision support only. Data can be incomplete, delayed or wrong. The tool never submits orders and cannot predict earnings surprises or breaking news.")
