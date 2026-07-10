from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import SignalEngine


ROOT = Path(__file__).parent
APP_STATE_VERSION = 13
CANDIDATE_SCHEMA_FIELDS = (
    "setup_status", "checklist", "darvas", "company", "catalyst",
    "setup_type", "a_plus_score", "reversal_watch", "extended_watch",
    "catalyst_analysis", "holding_plan", "move_quality", "advantage_profile",
)


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def candidate_schema_is_current(candidates: list) -> bool:
    return all(
        all(hasattr(candidate, field) for field in CANDIDATE_SCHEMA_FIELDS)
        for candidate in candidates
    )


st.set_page_config(page_title="Options Signal Desk", page_icon="📈", layout="wide")

# Streamlit preserves Python objects across hot reloads. Clear results created by an
# older Candidate schema before the UI attempts to read newly added fields.
saved_candidates = st.session_state.get("candidates", [])
if (
    st.session_state.get("app_state_version") != APP_STATE_VERSION
    or not candidate_schema_is_current(saved_candidates)
):
    for key in ("candidates", "errors", "scan_time"):
        st.session_state.pop(key, None)
    st.session_state["app_state_version"] = APP_STATE_VERSION

st.title("Options Signal Desk")
st.caption("Dylan Playbook V2: Market → theme → story → catalyst → stage → leadership → structure → confirmation → option → risk.")
st.caption("Only TRADE SETUP names have passed the live, liquid, affordable contract gate; WATCH names may appear before a contract qualifies.")
st.caption("MOVE WATCH means the move is worth studying, but it is not an approved entry.")
st.caption("PUT/CALL REVERSAL WATCH means the prior move is stretched; it is not an entry until the underlying confirms a reversal through structure and volume.")
st.caption("EXTENDED WATCH means momentum remains intact but chasing is blocked until a new base, hold, or retest forms.")
st.caption("Hold clock: TRADE SETUP ideas default to 3-5 trading days, shortened near earnings, expiration, or failed structure.")
st.caption("Move source check: separates real news + volume moves from relief bounces, pre-earnings positioning, and index/rebalance flow.")
st.caption("CAG-style move hunter: looks for two-day bounce/fade patterns, then waits for hold or rejection confirmation.")
st.caption("Small-account edge: favors affordable liquid contracts, clean levels, and theme names like Restaurants.")
st.caption("Balanced radar: up to 3 CALL names and 3 PUT names. The app never changes direction merely to fill a quota.")

config = load_config()
with st.sidebar:
    st.header("Risk controls")
    account = st.number_input("Account size ($)", 100, 100000, int(config["account_size"]), 50)
    risk_pct = st.slider("Maximum premium risk per trade", 1, 20, int(config["max_risk_per_trade_pct"]), 1)
    minimum_confidence = st.slider("Minimum model confidence", 50, 75, int(config["minimum_confidence"]), 1)
    automatic_discovery = st.toggle("Automatic market discovery", value=bool(config.get("automatic_discovery", True)))
    discovery_limit = st.slider("Stocks sent to full news analysis", 10, 30, int(config.get("discovery_limit", 20)), 5)
    move_discovery_limit = st.slider("CAG-style bounce/fade stocks analyzed", 5, 40, int(config.get("move_discovery_limit", 20)), 5)
    theme_options = list(config.get("theme_universes", {}).keys())
    enabled_themes = st.multiselect(
        "Theme lanes",
        theme_options,
        default=[theme for theme in config.get("enabled_theme_universes", []) if theme in theme_options],
    )
    st.caption(
        f"Discovery keeps {len(config.get('discovery_universe', []))} core symbols and adds the live top "
        f"{config.get('top_market_universe_size', 0):,} U.S.-listed stocks, then fully analyzes the strongest movers."
    )
    st.caption("A second news lane adds fresh earnings, FDA, guidance, contract, acquisition, partnership and analyst-action names before ranking.")
    st.caption("A third move-hunter lane adds stocks bouncing after a hard selloff, fading after a pop, or moving on high volume.")
    st.caption("Theme lanes force groups like Restaurants into the scan before the broad-market ranking runs.")
    watchlist = st.text_area("Watchlist", ", ".join(config["watchlist"]))
    st.warning("A small account should not target fixed daily income. One long option can lose its entire premium.")

config["account_size"] = account
config["max_risk_per_trade_pct"] = risk_pct
config["minimum_confidence"] = minimum_confidence
config["automatic_discovery"] = automatic_discovery
config["discovery_limit"] = discovery_limit
config["move_discovery_limit"] = move_discovery_limit
config["enabled_theme_universes"] = enabled_themes
config["watchlist"] = [s.strip().upper() for s in watchlist.split(",") if s.strip()]
maximum_stock_price = max(
    float(config["minimum_stock_price"]),
    float(account) * float(config.get("max_stock_price_per_account_dollar", .4)),
)
st.info(
    f"Account-scaled universe: stocks from ${config['minimum_stock_price']:.0f} to ${maximum_stock_price:,.0f}. "
    f"Current maximum premium risk: ${account * risk_pct / 100:,.0f} per contract."
)

if st.button("Run market scan", type="primary", use_container_width=True):
    with st.spinner("Reading prices, options chains, earnings and recent headlines…"):
        engine = SignalEngine(config)
        candidates, errors = engine.scan()
        st.session_state["candidates"] = candidates
        st.session_state["errors"] = errors
        st.session_state["scan_time"] = datetime.now().astimezone().strftime("%Y-%m-%d %I:%M:%S %p %Z")

st.divider()
st.subheader("Type any stock for Dave's deep dive")
st.caption("Use this for quality names like AAPL, BROS, CAVA, TSLA, NVDA, ULTA, HIMS, or any ticker you want to study.")
with st.form("deep_dive_form"):
    deep_symbol = st.text_input("Ticker", value=st.session_state.get("last_deep_symbol", "AAPL")).upper().strip()
    deep_submit = st.form_submit_button("Analyze this stock", use_container_width=True)
if deep_submit and deep_symbol:
    with st.spinner(f"Building full deep dive for {deep_symbol}..."):
        try:
            st.session_state["deep_dive"] = SignalEngine(config).deep_dive(deep_symbol)
            st.session_state["last_deep_symbol"] = deep_symbol
            st.session_state.pop("deep_dive_error", None)
        except Exception as exc:
            st.session_state["deep_dive_error"] = f"{deep_symbol}: {exc}"
            st.session_state.pop("deep_dive", None)

if st.session_state.get("deep_dive_error"):
    st.error(st.session_state["deep_dive_error"])

if st.session_state.get("deep_dive"):
    dive = st.session_state["deep_dive"]
    st.markdown(f"### {dive['symbol']} deep dive - {dive['quality']['label']} ({dive['quality']['score']}/100)")
    metric_cols = st.columns(5)
    metric_cols[0].metric("Price", f"${dive['history']['latest_price']:.2f}")
    metric_cols[1].metric("6mo return", f"{dive['history']['six_month_return_pct']:+.1f}%")
    metric_cols[2].metric("20d return", f"{dive['history']['twenty_day_return_pct']:+.1f}%")
    metric_cols[3].metric("Max drawdown", f"{dive['history']['max_drawdown_pct']:+.1f}%")
    metric_cols[4].metric("Trend", dive["history"]["trend_label"])

    history_frame = pd.DataFrame(dive["historical_rows"])
    if not history_frame.empty:
        line = go.Figure()
        line.add_trace(go.Scatter(x=history_frame["date"], y=history_frame["close"], mode="lines", name="Close"))
        line.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Close")
        st.plotly_chart(line, use_container_width=True)

    tabs = st.tabs(["Summary", "News + community proxy", "Financials", "Historical data", "Earnings / press releases"])
    with tabs[0]:
        st.write(f"**{dive['profile']['name']}** - {dive['profile']['sector']} / {dive['profile']['industry']}")
        st.write(f"**Themes:** {', '.join(dive['themes']) or 'No theme lane match'}")
        st.write(dive["profile"]["business"] or "Business summary unavailable.")
        col_up, col_down = st.columns(2)
        with col_up:
            st.markdown("**Why it could go up**")
            for item in dive["bull_case"] or ["No clear bull case yet."]:
                st.write(f"- {item}")
        with col_down:
            st.markdown("**What could go wrong**")
            for item in dive["bear_case"] or ["No major warnings found yet."]:
                st.write(f"- {item}")
    with tabs[1]:
        st.markdown("**Community/news proxy**")
        st.caption("This uses recent headline tone and analyst data as a proxy. Verify Reddit/X/Stocktwits manually before trading.")
        st.json(dive["news_summary"])
        for headline in dive["headlines"][:8]:
            mood = "positive" if headline["sentiment"] > .1 else "negative" if headline["sentiment"] < -.1 else "neutral"
            st.markdown(f"- [{headline['title']}]({headline['link']}) - {mood}")
            if headline.get("summary"):
                st.caption(headline["summary"])
    with tabs[2]:
        st.markdown("**Financial snapshot**")
        st.json(dive["financials"])
        st.markdown("**Analyst snapshot**")
        st.json(dive["analyst"])
    with tabs[3]:
        st.dataframe(history_frame.sort_values("date", ascending=False), hide_index=True, use_container_width=True)
    with tabs[4]:
        st.metric("Next earnings date", dive["earnings"])
        if dive["press_release_headlines"]:
            for headline in dive["press_release_headlines"][:6]:
                st.markdown(f"- [{headline['title']}]({headline['link']})")
        else:
            st.info("No recent earnings-call or press-release style headline found in the news feed.")

if "candidates" not in st.session_state:
    st.info("Press **Run market scan**. The model may return no trade when signals are weak or contracts exceed your risk cap.")
    st.stop()

st.caption(f"Last scan: {st.session_state['scan_time']}. Quotes may be delayed; confirm every price in Robinhood.")
candidates = st.session_state["candidates"]
if not candidate_schema_is_current(candidates):
    for key in ("candidates", "errors", "scan_time"):
        st.session_state.pop(key, None)
    st.warning("Dave updated the app after your last scan, so I cleared the old cached results. Press **Run market scan** again to get fresh candidates.")
    st.stop()
if not candidates:
    st.error("No candidate passed the evidence and risk filters. No trade is a valid result.")
else:
    st.subheader("Dave's 3-stock weekly study list")
    st.caption("These are the best current study candidates from the scan, not a promise to trade. Confirm price, contract, news, and entry level in Robinhood.")
    weekly = sorted(
        candidates,
        key=lambda c: (
            c.advantage_profile["score"],
            c.setup_status == "TRADE SETUP",
            c.a_plus_score,
            c.confidence,
        ),
        reverse=True,
    )[:3]
    if weekly:
        weekly_cols = st.columns(len(weekly))
        for column, c in zip(weekly_cols, weekly):
            with column:
                st.markdown(f"#### {c.symbol} - {c.direction}")
                st.write(f"**{c.setup_status}**")
                st.write(f"Edge: {c.advantage_profile['label']} ({c.advantage_profile['score']}/100)")
                st.write(f"Theme: {', '.join(c.advantage_profile['themes']) or 'No theme'}")
                st.write(f"Price: ${c.price:.2f}")
                st.write(f"Hold: {c.holding_plan['suggested_hold']}")
                st.write(f"Move source: {c.move_quality['source_type']}")
                st.write(f"Contract: {c.option['contract'] if c.option else 'None found'}")
                top_headline = c.headlines[0]["title"] if c.headlines else "No recent headline found"
                st.caption(top_headline)
    else:
        st.info("No weekly study candidates yet. Run a scan or loosen filters carefully.")

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
        "Theme": ", ".join(c.advantage_profile["themes"]) or "—",
        "Small-account edge": f"{c.advantage_profile['label']} ({c.advantage_profile['score']}/100)",
        "Move source": c.move_quality["source_type"],
        "Suggested hold": c.holding_plan["suggested_hold"],
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
                st.write(f"**Why it matters / what to verify:** {c.catalyst_analysis}")
                st.markdown("**Source of move / bounce check**")
                st.write(f"{c.move_quality['label']} — {c.move_quality['score']}/100 source quality")
                st.json({
                    "source type": c.move_quality["source_type"],
                    "latest daily move %": c.move_quality["latest_daily_move"],
                    "previous daily move %": c.move_quality["previous_daily_move"],
                    "latest volume vs 30d": c.move_quality["latest_volume_vs_30d"],
                })
                for item in c.move_quality["flags"] or ["No source-of-move warnings detected."]:
                    st.write(f"- {item}")
                st.markdown("Verify before entry:")
                for item in c.move_quality["verify"]:
                    st.write(f"- {item}")
                st.markdown("**Small-account advantage**")
                st.write(f"{c.advantage_profile['label']} — {c.advantage_profile['score']}/100")
                st.json({
                    "themes": c.advantage_profile["themes"],
                    "max premium risk": c.advantage_profile["max_premium_risk"],
                    "ideal contract cost": c.advantage_profile["ideal_contract_cost"],
                    "contract cost": c.advantage_profile["contract_cost"],
                })
                st.markdown("Edge positives:")
                for item in c.advantage_profile["positives"] or ["No small-account advantages detected yet."]:
                    st.write(f"- {item}")
                st.markdown("Edge warnings:")
                for item in c.advantage_profile["warnings"] or ["No major small-account warnings detected."]:
                    st.write(f"- {item}")
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
                st.markdown("**Hold / exit clock**")
                st.write(f"Suggested hold: {c.holding_plan['suggested_hold']}")
                st.write(c.holding_plan["rationale"])
                st.write(f"Review cadence: {c.holding_plan['review_cadence']}")
                st.markdown("Exit early if:")
                for item in c.holding_plan["exit_early_if"]:
                    st.write(f"- {item}")
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
                if headline.get("summary"):
                    st.caption(headline["summary"])

errors = st.session_state.get("errors", [])
if errors:
    with st.expander("Data-source warnings"):
        st.write("\n".join(errors))

st.divider()
st.caption("Decision support only. Data can be incomplete, delayed or wrong. The tool never submits orders and cannot predict earnings surprises or breaking news.")
