from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import SignalEngine


ROOT = Path(__file__).parent
APP_STATE_VERSION = 21
USER_AGREEMENT_VERSION = "2026-07-14-v2"
CANDIDATE_SCHEMA_FIELDS = (
    "setup_status", "checklist", "darvas", "company", "catalyst",
    "setup_type", "a_plus_score", "reversal_watch", "extended_watch",
    "catalyst_analysis", "holding_plan", "move_quality", "advantage_profile",
    "premarket_context",
)


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


USER_AGREEMENT_TEXT = """
### Dylan Dave Options Desk User Agreement

Last updated: July 14, 2026

By accessing or using Dylan Dave Options Desk ("the Platform"), you confirm that you are at least 18 years old, have read this agreement, understand it, and voluntarily agree to its terms. If you do not agree, you must not use the Platform.

1. **Educational purposes only.** The Platform provides general market information, research tools, calculations, and educational content. It is not a brokerage, registered investment adviser, financial adviser, commodity trading adviser, legal adviser, tax adviser, or fiduciary. Nothing provided by the Platform constitutes personalized financial, investment, legal, or tax advice.

2. **Not registered or regulator-approved.** Dylan Dave Options Desk and its creator are not presented as SEC-registered, state-registered, FINRA-registered, broker-dealer approved, investment-adviser approved, or otherwise approved by any financial regulator. No regulator has reviewed, endorsed, or approved the app's signals, scoring, watchlists, or educational content.

3. **No recommendations or trade instructions.** Stock names, option contracts, market observations, alerts, scores, rankings, examples, watchlists, or other Platform outputs are presented for informational and educational purposes only. Nothing displayed should be interpreted as an instruction, solicitation, endorsement, or recommendation to buy, sell, hold, or short any security or option. The Platform does not evaluate your financial condition, experience, debts, income, objectives, risk tolerance, or whether a particular trade is suitable for you.

4. **Do your own research.** You must do your own independent research and due diligence before making any financial decision. Do not rely only on the app, a social-media post, a headline, or another user's result.

5. **Options involve substantial risk.** Options trading is speculative and can result in significant financial loss. A purchased option may lose 100% of its premium. Certain option-selling strategies may expose traders to losses exceeding the premium received and, in some cases, potentially unlimited losses. Short-dated options can lose value rapidly because of price movement, time decay, changes in implied volatility, liquidity, and bid-ask spreads. Past performance, examples, simulations, and hypothetical results do not guarantee future performance. Only trade with money you can afford to lose.

6. **No guarantee of accuracy or results.** Market data, prices, news, earnings dates, option chains, Greeks, volatility measurements, sentiment indicators, scores, calculations, and other information may be delayed, incomplete, inaccurate, unavailable, or affected by technical errors. Any "confidence," "opportunity," or similar score is an analytical estimate, not a guaranteed probability of success. The Platform makes no promise or guarantee regarding profits, winning trades, income, account growth, accuracy, availability, or any particular outcome.

7. **Independent verification required.** Before making any decision, you are responsible for independently verifying all information through your broker and other reliable sources, including the ticker, strike price, expiration date, option type, current price, bid-ask spread, volume, open interest, earnings dates, company announcements, relevant news, contract liquidity, brokerage availability, order details, maximum possible loss, and your ability to accept that loss. You are solely responsible for reviewing and approving every order before submitting it.

8. **Assumption of risk.** You voluntarily assume all risks arising from your use of the Platform and from any investment or trading decision you make. You understand that you, not the Platform, its creator, operators, contributors, data providers, or affiliates, are solely responsible for your trades, decisions, profits, losses, taxes, and financial consequences.

9. **Limitation of liability.** To the fullest extent permitted by applicable law, Dylan Dave Options Desk and its creator, operators, contributors, affiliates, and data providers will not be liable for trading losses, lost profits, missed opportunities, incorrect or delayed information, technical failures, service interruptions, reliance on Platform content, or decisions made using the Platform. Nothing in this agreement excludes liability that cannot legally be excluded, including liability resulting from fraud, intentional misconduct, or other legally non-waivable conduct.

10. **No professional relationship.** Using the Platform does not create an adviser-client, broker-client, fiduciary, attorney-client, partnership, employment, or other professional relationship. For personalized financial, investment, legal, or tax advice, consult an appropriately licensed professional. You may independently check investment-professional registration through official tools such as SEC/Investor.gov IAPD and FINRA BrokerCheck.

11. **Final acknowledgment.** By selecting "I Understand and Agree" or continuing to use the Platform, you acknowledge that you have read and understood this agreement, the Platform provides educational information and not personalized advice, options trading may result in the loss of your entire investment, you are solely responsible for every trading decision you make, and no profit or investment result has been promised or guaranteed.

12. **Social media and marketing disclaimer.** Any short-form or social-media content connected to the Platform should be treated as educational content only, not personalized financial advice or a recommendation to trade. Options involve substantial risk, including the possible loss of 100% of your investment. Results are not guaranteed. Conduct your own research and consult a licensed professional. Avoid language such as "guaranteed profit," "can't lose," "easy money," or presenting a confidence score as a true win probability.

This agreement is a practical protective notice, not a substitute for attorney-drafted Terms of Service. If this app becomes a real paid business, have a licensed attorney review it.
"""


def secret_value(name: str, default: object = "") -> object:
    """Read Streamlit secrets safely both locally and on Community Cloud."""
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def secret_bool(name: str, default: bool = False) -> bool:
    value = secret_value(name, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def secret_list(name: str) -> list[str]:
    value = secret_value(name, "")
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def normalize_access_code(code: str) -> str:
    return code.strip().upper().replace(" ", "")


def month_key(months_back: int = 0) -> str:
    now = datetime.now().astimezone()
    year = now.year
    month = now.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return f"{year:04d}{month:02d}"


def rotating_period_keys(period: str, grace_periods: int) -> list[str]:
    period = period.strip().lower()
    grace_periods = max(0, min(grace_periods, 3))
    now = datetime.now().astimezone()
    if period == "daily":
        return [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(grace_periods + 1)]
    return [month_key(i) for i in range(grace_periods + 1)]


def rotating_member_code(email: str, secret: str, period_key: str) -> str:
    normalized_email = email.strip().lower()
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{normalized_email}|{period_key}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()
    return f"DD-{period_key}-{digest[:4]}-{digest[4:8]}"


def rotating_access_code_is_valid(email: str, submitted_code: str) -> bool:
    secret = str(secret_value("ROTATING_ACCESS_SECRET", "")).strip()
    if not secret or not email.strip() or not submitted_code.strip():
        return False
    period = str(secret_value("ROTATING_ACCESS_PERIOD", "monthly")).strip().lower()
    try:
        grace_periods = int(secret_value("ROTATING_ACCESS_GRACE_PERIODS", 0))
    except (TypeError, ValueError):
        grace_periods = 0

    submitted = normalize_access_code(submitted_code)
    for period_key in rotating_period_keys(period, grace_periods):
        expected = normalize_access_code(rotating_member_code(email, secret, period_key))
        if hmac.compare_digest(submitted, expected):
            return True
    return False


def first_query_value(*names: str) -> str:
    """Return the first non-empty Streamlit query-param value for any name."""
    for name in names:
        try:
            value = st.query_params.get(name, "")
        except Exception:
            value = ""
        if isinstance(value, list):
            value = value[0] if value else ""
        value = str(value).strip()
        if value:
            return value
    return ""


def stripe_object_value(obj: object, key: str, default: object = None) -> object:
    """Read values from Stripe objects whether they behave like dicts or objects."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def stripe_checkout_email(session: object) -> str:
    customer_details = stripe_object_value(session, "customer_details")
    customer = stripe_object_value(session, "customer")
    return str(
        stripe_object_value(customer_details, "email")
        or stripe_object_value(session, "customer_email")
        or stripe_object_value(customer, "email")
        or ""
    ).strip()


def stripe_checkout_is_paid(session: object) -> bool:
    status = str(stripe_object_value(session, "status", "")).lower()
    payment_status = str(stripe_object_value(session, "payment_status", "")).lower()
    subscription = stripe_object_value(session, "subscription")
    subscription_status = str(stripe_object_value(subscription, "status", "")).lower()

    return status == "complete" and (
        payment_status == "paid"
        or subscription_status in {"active", "trialing"}
    )


def stripe_checkout_matches_guardrails(session: object) -> tuple[bool, str]:
    """Optional extra checks so another Stripe product cannot unlock the app by accident."""
    allowed_payment_link = str(secret_value("STRIPE_ALLOWED_PAYMENT_LINK_ID", "")).strip()
    if allowed_payment_link:
        session_payment_link = str(stripe_object_value(session, "payment_link", "")).strip()
        if session_payment_link and session_payment_link != allowed_payment_link:
            return False, "That Stripe payment was not for Dylan Dave Options Desk."

    expected_amount_raw = str(secret_value("STRIPE_EXPECTED_AMOUNT_CENTS", "")).strip()
    if expected_amount_raw:
        try:
            expected_amount = int(expected_amount_raw)
        except ValueError:
            expected_amount = 0
        amount_total = stripe_object_value(session, "amount_total", None)
        if expected_amount and amount_total is not None and int(amount_total) != expected_amount:
            return False, "That Stripe payment amount does not match this membership."

    return True, ""


def verify_stripe_checkout_session(session_id: str) -> tuple[bool, str, str]:
    """Verify a Stripe Checkout/Payment Link return and return (ok, email, message)."""
    stripe_secret_key = str(secret_value("STRIPE_SECRET_KEY", "")).strip()
    if not stripe_secret_key:
        return (
            False,
            "",
            "Payment returned from Stripe, but automatic unlock is not configured yet. "
            "Add STRIPE_SECRET_KEY in Streamlit secrets.",
        )

    try:
        import stripe  # type: ignore
    except Exception:
        return (
            False,
            "",
            "Payment returned from Stripe, but the Stripe package is not installed yet. "
            "Redeploy after requirements.txt updates.",
        )

    try:
        stripe.api_key = stripe_secret_key
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["customer", "subscription"],
        )
    except Exception as exc:
        return False, "", f"Stripe could not verify this payment yet: {exc}"

    if not stripe_checkout_is_paid(session):
        return False, "", "Stripe did not confirm a completed paid subscription for this checkout session."

    guardrail_ok, guardrail_message = stripe_checkout_matches_guardrails(session)
    if not guardrail_ok:
        return False, "", guardrail_message

    email = stripe_checkout_email(session)
    if not email:
        return False, "", "Stripe verified payment, but no subscriber email came back from checkout."

    return True, email, "Payment verified by Stripe. Member access unlocked."


def current_member_code_for_email(email: str) -> tuple[str, str]:
    secret = str(secret_value("ROTATING_ACCESS_SECRET", "")).strip()
    if not secret or not email.strip():
        return "", ""
    period = str(secret_value("ROTATING_ACCESS_PERIOD", "monthly")).strip().lower()
    period_key = rotating_period_keys(period, 0)[0]
    return rotating_member_code(email, secret, period_key), period_key


def clear_payment_query_params() -> None:
    try:
        for name in ("session_id", "checkout_session_id", "stripe_session_id"):
            if name in st.query_params:
                del st.query_params[name]
    except Exception:
        pass


def stripe_payment_link_for_customer(payment_link: str) -> str:
    """Add optional safe customer-facing Stripe URL parameters."""
    promo_code = str(secret_value("STRIPE_PREFILLED_PROMO_CODE", "")).strip()
    if not payment_link or not promo_code:
        return payment_link

    parsed = urlsplit(payment_link)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["prefilled_promo_code"] = promo_code
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        )
    )


def require_user_agreement() -> None:
    if st.session_state.get("accepted_terms_version") == USER_AGREEMENT_VERSION:
        return

    st.subheader("Before you use the desk")
    st.write(
        "Please accept the user agreement. This protects the project and makes it clear "
        "that every trade decision stays with the person placing the trade."
    )
    with st.expander("Read the full user agreement", expanded=True):
        st.markdown(USER_AGREEMENT_TEXT)

    signer_name = st.text_input("Type your full name to accept", key="agreement_name")
    accepted = st.checkbox(
        "I am at least 18 years old. I have read and accept the Risk Disclosure and User Agreement, understand that options trading can result in substantial losses, and accept full responsibility for my decisions.",
        key="agreement_checkbox",
    )
    if st.button("I Understand and Agree", type="primary", use_container_width=True):
        if not signer_name.strip() or not accepted:
            st.error("Type your name and check the agreement box before entering.")
        else:
            st.session_state["accepted_terms_version"] = USER_AGREEMENT_VERSION
            st.session_state["accepted_terms_name"] = signer_name.strip()
            st.session_state["accepted_terms_time"] = datetime.now().astimezone().isoformat()
            st.rerun()
    st.stop()


def require_subscription_if_enabled() -> None:
    stripe_payment_link = str(secret_value("STRIPE_PAYMENT_LINK", "")).strip()
    valid_access_codes = {
        code.strip().upper()
        for code in secret_list("ACCESS_CODES")
        if code.strip()
    }
    rotating_secret = str(secret_value("ROTATING_ACCESS_SECRET", "")).strip()
    subscription_enabled = secret_bool(
        "SUBSCRIPTION_ENABLED",
        bool(stripe_payment_link or valid_access_codes or rotating_secret),
    )
    if not subscription_enabled:
        return

    checkout_session_id = first_query_value("session_id", "checkout_session_id", "stripe_session_id")
    if checkout_session_id and not st.session_state.get("subscriber_access_granted"):
        verified, email, message = verify_stripe_checkout_session(checkout_session_id)
        if verified:
            st.session_state["subscriber_access_granted"] = True
            st.session_state["subscriber_email"] = email
            st.session_state["stripe_unlock_message"] = message
            member_code, period_key = current_member_code_for_email(email)
            if member_code:
                st.session_state["subscriber_current_code"] = member_code
                st.session_state["subscriber_current_period"] = period_key
            clear_payment_query_params()
            st.rerun()
        else:
            st.warning(message)

    if st.session_state.get("subscriber_access_granted"):
        st.sidebar.success("Member access active for this browser session")
        if st.session_state.get("stripe_unlock_message"):
            st.sidebar.success(str(st.session_state.pop("stripe_unlock_message")))
        member_code = st.session_state.get("subscriber_current_code")
        member_period = st.session_state.get("subscriber_current_period")
        if member_code:
            st.sidebar.caption(f"Save this member code for {member_period}:")
            st.sidebar.code(str(member_code), language="text")
        return

    price_label = str(secret_value("SUBSCRIPTION_PRICE_LABEL", "$24.99/month")).strip() or "$24.99/month"
    support_email = str(secret_value("SUPPORT_EMAIL", "")).strip()

    st.subheader("Dylan Dave Options Desk membership")
    st.metric("Monthly subscription", price_label)
    st.write(
        "This link can be shared, but app access does not unlock for a new visitor until "
        "they subscribe or enter their own member access code."
    )
    st.info(
        "Unpaid visitors see this membership page first. After payment, Stripe can send them "
        "back here and unlock the scanner automatically. The private code box stays here as a backup."
    )

    if stripe_payment_link:
        st.link_button(
            f"Subscribe for {price_label}",
            stripe_payment_link_for_customer(stripe_payment_link),
            use_container_width=True,
        )
        if str(secret_value("STRIPE_PREFILLED_PROMO_CODE", "")).strip():
            st.caption("A Stripe promo code is prefilled at checkout when Stripe allows that code.")
    else:
        st.info(
            "Subscription checkout is ready, but Stripe is not connected yet. "
            "Add STRIPE_PAYMENT_LINK in Streamlit secrets so unpaid visitors can pay."
        )

    st.caption(
        "Stripe promo codes are discount codes created in Stripe. The member access code below "
        "is only a backup app-unlock code after payment."
    )

    with st.form("member_access_form"):
        email = st.text_input("Subscriber email")
        code = st.text_input("Member access code", type="password")
        submitted = st.form_submit_button("Unlock member access", use_container_width=True)

    if submitted:
        static_code_ok = valid_access_codes and normalize_access_code(code) in valid_access_codes
        rotating_code_ok = rotating_access_code_is_valid(email, code)
        if static_code_ok or rotating_code_ok:
            st.session_state["subscriber_access_granted"] = True
            st.session_state["subscriber_email"] = email.strip()
            st.rerun()
        else:
            st.error("Access code not recognized. Check the code Dylan sent after payment.")

    if support_email:
        st.caption(f"Need help with access? Email {support_email}.")

    st.caption(
        "Simple membership mode uses Stripe Payment Links plus private Streamlit secrets. "
        "Sharing the app link will not share an unlocked session. Rotating codes can be tied to a subscriber email "
        "and refresh each billing period. "
        "For fully automated subscriptions, add Stripe Checkout webhooks and a subscriber database."
    )
    st.stop()


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
    for key in ("candidates", "errors", "rejections", "scan_time"):
        st.session_state.pop(key, None)
    st.session_state["app_state_version"] = APP_STATE_VERSION

st.title("Options Signal Desk")
st.warning(
    "Public safety note: this dashboard is educational decision support only. "
    "It is not a registered or regulator-approved financial adviser, does not place trades, "
    "does not provide personalized financial advice, and cannot guarantee profit. "
    "Do your own research and verify live quotes, earnings, liquidity, bid/ask spreads, "
    "and tradability in your own brokerage account before risking money."
)
require_user_agreement()
require_subscription_if_enabled()
st.caption("Dylan Playbook V2: Market → theme → story → catalyst → stage → leadership → structure → confirmation → option → risk.")
st.caption("Only TRADE SETUP names have passed the live, liquid, affordable contract gate; WATCH names may appear before a contract qualifies.")
st.caption("STUDY ONLY names are educational radar ideas with a theme, move, or catalyst clue; they are not entries.")
st.caption("MOVE WATCH means the move is worth studying, but it is not an approved entry.")
st.caption("PUT/CALL REVERSAL WATCH means the prior move is stretched; it is not an entry until the underlying confirms a reversal through structure and volume.")
st.caption("PUT FADE WATCH means a prior pop is failing; it is not an entry until price rejects the failed-pop area and Robinhood confirms the contract quote.")
st.caption("EXTENDED WATCH means momentum remains intact but chasing is blocked until a new base, hold, or retest forms.")
st.caption("Hold clock: TRADE SETUP ideas default to 3-5 trading days, shortened near earnings, expiration, or failed structure.")
st.caption("Move source check: separates real news + volume moves from relief bounces, pre-earnings positioning, and index/rebalance flow.")
st.caption("Premarket/open trap detector: premarket alone is not enough; Dave waits for 9:45-10:30 ET confirmation, VWAP hold, or rejection.")
st.caption("CAG-style move hunter: looks for two-day bounce/fade patterns, then waits for hold or rejection confirmation.")
st.caption("Small-account edge: favors affordable liquid contracts, clean levels, and theme names like Restaurants.")
st.caption("Balanced radar: up to 3 CALL names and 3 PUT names. The app never changes direction merely to fill a quota.")

config = load_config()
with st.sidebar:
    st.header("Risk controls")
    grind_mode = st.toggle("Small-account grind mode", value=bool(config.get("small_account_grind_mode", True)))
    account = st.number_input("Account size ($)", 100, 100000, int(config["account_size"]), 50, key="account_size_v19")
    account_goal = st.number_input("Account goal ($)", 300, 100000, int(config.get("account_goal", 1000)), 50, key="account_goal_v19")
    risk_pct = st.slider("Maximum contract cap (% of account)", 1, 100, int(config["max_risk_per_trade_pct"]), 1, key="premium_cap_v19")
    st.caption(
        "Grind mode is built for low-priced stocks and contracts that fit the account. "
        "A smaller cap gives more survival; a bigger cap gives more risk."
    )
    minimum_confidence = st.slider("Minimum trade confidence", 50, 90, int(config["minimum_confidence"]), 1)
    high_confidence_only = st.toggle(
        "Only show names at or above confidence target",
        value=bool(config.get("high_confidence_only", False)),
    )
    st.caption("Leave this off when your priority is filling the 3 CALL + 3 PUT budget slate; turn it on for strict 80+ only.")
    automatic_discovery = st.toggle("Automatic market discovery", value=bool(config.get("automatic_discovery", True)))
    discovery_limit = st.slider("Stocks sent to full news analysis", 10, 30, int(config.get("discovery_limit", 20)), 5)
    move_discovery_limit = st.slider("CAG-style bounce/fade stocks analyzed", 5, 40, int(config.get("move_discovery_limit", 20)), 5)
    theme_discovery_limit = st.slider("Theme stocks fully analyzed", 7, 35, int(config.get("theme_discovery_limit", 10)), 1)
    broad_discovery_pool_size = st.slider("Broad pool pre-ranked", 100, 1000, int(config.get("broad_discovery_pool_size", 200)), 50)
    max_symbols_to_analyze = st.slider("Max stocks fully analyzed per scan", 10, 80, int(config.get("max_symbols_to_analyze", 60)), 5)
    theme_options = list(config.get("theme_universes", {}).keys())
    enabled_themes = st.multiselect(
        "Theme lanes",
        theme_options,
        default=[theme for theme in config.get("enabled_theme_universes", []) if theme in theme_options],
    )
    st.caption(
        f"Discovery keeps {len(config.get('discovery_universe', []))} core symbols, reads the live top "
        f"{config.get('top_market_universe_size', 0):,} U.S.-listed stocks, and pre-ranks the first "
        f"{broad_discovery_pool_size:,} affordable names before full analysis."
    )
    st.caption("A second news lane adds fresh earnings, FDA, guidance, contract, acquisition, partnership and analyst-action names before ranking.")
    st.caption("A third move-hunter lane adds stocks bouncing after a hard selloff, fading after a pop, or moving on high volume.")
    st.caption("Theme lanes are pre-ranked first, then the best names go into full news/options analysis so the scan finishes faster.")
    if config.get("budget_qualified_main_list", True):
        st.caption("Main slate requires an affordable contract; names like VERA are excluded if the option premium breaks the budget.")
    watchlist = st.text_area("Watchlist", ", ".join(config["watchlist"]))
    st.warning("A small account should not target fixed daily income. One long option can lose its entire premium. Grind mode favors survival over one-shot all-in contracts.")

config["small_account_grind_mode"] = grind_mode
config["account_size"] = account
config["account_goal"] = account_goal
config["max_risk_per_trade_pct"] = risk_pct
if grind_mode:
    config["minimum_stock_price"] = 5
    config["max_stock_price_per_account_dollar"] = 0.25
else:
    config["minimum_stock_price"] = 10
    config["max_stock_price_per_account_dollar"] = 0.4
config["minimum_confidence"] = minimum_confidence
config["high_confidence_only"] = high_confidence_only
if high_confidence_only:
    config["watch_minimum_confidence"] = minimum_confidence
config["automatic_discovery"] = automatic_discovery
config["discovery_limit"] = discovery_limit
config["move_discovery_limit"] = move_discovery_limit
config["theme_discovery_limit"] = theme_discovery_limit
config["broad_discovery_pool_size"] = broad_discovery_pool_size
config["max_symbols_to_analyze"] = max_symbols_to_analyze
config["enabled_theme_universes"] = enabled_themes
config["watchlist"] = [s.strip().upper() for s in watchlist.split(",") if s.strip()]
maximum_stock_price = max(
    float(config["minimum_stock_price"]),
    float(account) * float(config.get("max_stock_price_per_account_dollar", .4)),
)
st.info(
    f"Grind path: USD {account:,.0f} to USD {account_goal:,.0f}. "
    f"Low-stock universe: USD {config['minimum_stock_price']:.0f} to USD {maximum_stock_price:,.0f}. "
    f"Current maximum option premium cap: USD {account * risk_pct / 100:,.0f} per contract. "
    "The 6-stock slate only counts names with a contract inside that cap."
)

if st.button("Run market scan", type="primary", use_container_width=True):
    with st.spinner("Reading prices, options chains, earnings and recent headlines…"):
        engine = SignalEngine(config)
        candidates, errors = engine.scan()
        st.session_state["candidates"] = candidates
        st.session_state["errors"] = errors
        st.session_state["rejections"] = getattr(engine, "rejection_report", [])
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
rejections = st.session_state.get("rejections", [])
if not candidate_schema_is_current(candidates):
    for key in ("candidates", "errors", "rejections", "scan_time"):
        st.session_state.pop(key, None)
    st.warning("Dave updated the app after your last scan, so I cleared the old cached results. Press **Run market scan** again to get fresh candidates.")
    st.stop()
if not candidates:
    if config.get("high_confidence_only", False):
        st.error(
            f"No candidate reached the {minimum_confidence}% confidence target with the current risk filters. "
            "That is not broken — it means the scanner did not find a clean high-confidence setup with an affordable option contract yet. "
            "You can raise Max stocks fully analyzed per scan, raise Broad pool pre-ranked, or turn off high-confidence-only to review study radar."
        )
    else:
        st.error("No candidate passed the evidence and risk filters. No trade is a valid result.")
else:
    if config.get("high_confidence_only", False):
        st.success(f"High-confidence mode is on: showing only names at or above {minimum_confidence}% confidence.")
    call_count = sum(c.direction == "CALL" for c in candidates)
    put_count = sum(c.direction == "PUT" for c in candidates)
    st.subheader("Dave's budget-qualified 6-stock slate")
    st.caption(
        f"Target is 3 CALL + 3 PUT for the USD {account:,.0f} grind account. Every name here must have an option contract "
        "inside the configured premium-risk cap. No expensive/no-contract names get forced into this slate."
    )
    if call_count < int(config.get("max_call_candidates", 3)) or put_count < int(config.get("max_put_candidates", 3)):
        st.warning(
            f"Budget slate is incomplete: {call_count}/3 CALL and {put_count}/3 PUT. "
            "Dave will not fake extra picks when the contracts are too expensive or the evidence is weak."
        )
    slate = sorted(
        candidates,
        key=lambda c: (
            c.direction == "CALL",
            c.advantage_profile["score"],
            c.setup_status == "TRADE SETUP",
            c.a_plus_score,
            c.confidence,
        ),
        reverse=True,
    )[:6]
    if slate:
        slate_cols = st.columns(3)
        for index, c in enumerate(slate):
            column = slate_cols[index % 3]
            with column:
                st.markdown(f"#### {c.symbol} - {c.direction}")
                st.write(f"**{c.setup_status}**")
                st.write(f"Confidence: **{c.confidence}%**")
                st.write(f"Edge: {c.advantage_profile['label']} ({c.advantage_profile['score']}/100)")
                st.write(f"Theme: {', '.join(c.advantage_profile['themes']) or 'No theme'}")
                st.write(f"Price: ${c.price:.2f}")
                st.write(f"Premium: ${c.option['estimated_cost_and_max_loss']:.2f}")
                st.write(f"Option tier: {c.option.get('quality_tier', 'standard')}")
                if c.option.get("quote_warning"):
                    st.warning(c.option["quote_warning"])
                st.write(f"Hold: {c.holding_plan['suggested_hold']}")
                st.write(f"Move source: {c.move_quality['source_type']}")
                st.write(f"Premarket/open: {c.premarket_context['label']} ({c.premarket_context['gate']})")
                st.write(f"Contract: {c.option['contract']}")
                top_headline = c.headlines[0]["title"] if c.headlines else "No recent headline found"
                st.caption(top_headline)
    else:
        st.info("No budget-qualified slate candidates yet. Run a deeper scan or loosen filters carefully.")

    call_metric, put_metric = st.columns(2)
    call_metric.metric("Budget CALL slate", f"{call_count}/3")
    put_metric.metric("Budget PUT slate", f"{put_count}/3")
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
        "Premarket/open": f"{c.premarket_context['label']} ({c.premarket_context['gate']})",
        "Suggested hold": c.holding_plan["suggested_hold"],
        "Affordable contract": c.option["contract"] if c.option else "None found",
        "Premium / max loss": f"${c.option['estimated_cost_and_max_loss']:.2f}" if c.option else "—",
        "Option tier": c.option.get("quality_tier", "—") if c.option else "—",
        "Earnings": c.earnings,
    } for c in candidates])
    st.dataframe(summary, hide_index=True, use_container_width=True)
    st.caption("*Confidence is a heuristic evidence score, not the historical win probability or a promise of profit.")

    for rank, c in enumerate(candidates, 1):
        with st.expander(
            f"#{rank} {c.symbol} — {c.setup_status} — {c.direction} — confidence {c.confidence}% — A+ {c.a_plus_score}/100",
            expanded=rank == 1,
        ):
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
                st.markdown("**Premarket vs open trap detector**")
                pre = c.premarket_context
                st.write(f"{pre['label']} - gate: **{pre['gate']}** - bias: **{pre['trade_bias']}**")
                st.json({
                    "confirmation window": pre["confirmation_window"],
                    "premarket direction": pre["premarket_direction"],
                    "premarket move %": pre["premarket_move_pct"],
                    "premarket high": pre["premarket_high"],
                    "premarket low": pre["premarket_low"],
                    "open price": pre["open_price"],
                    "current price": pre["current_price"],
                    "vwap": pre["vwap"],
                    "score": pre["score"],
                })
                st.write(pre["rule"])
                for item in pre["verify"]:
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
                st.metric("Model confidence", f"{c.confidence}%")
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
                if c.option.get("quote_warning"):
                    st.warning(c.option["quote_warning"])
                st.warning("Use a limit order. Recheck bid/ask, liquidity, news and the underlying chart immediately before entry.")
            else:
                st.info("No sufficiently liquid near-the-money contract fit the configured premium-risk limit. Do not stretch the risk cap.")
            st.subheader("Recent headlines")
            for headline in c.headlines[:6]:
                mood = "positive" if headline["sentiment"] > .1 else "negative" if headline["sentiment"] < -.1 else "neutral"
                st.markdown(f"- [{headline['title']}]({headline['link']}) — {mood}")
                if headline.get("summary"):
                    st.caption(headline["summary"])

qualified_alternates = [
    row for row in rejections
    if "lower-ranked" in str(row.get("Why rejected", "")).lower()
]
if qualified_alternates:
    st.subheader("Budget-qualified alternates Dave noticed")
    st.caption(
        "These names fit the account cap and had a usable contract estimate, but ranked below the selected 3 CALL / 3 PUT slate. "
        "This is where ideas like MARA PUT or SOFI CALL can still show up for manual review."
    )
    alternate_frame = pd.DataFrame(qualified_alternates)
    alternate_cols = [
        "Symbol", "Direction", "Status", "Confidence", "Price",
        "Premium / max loss", "Max allowed", "Why rejected", "Next move",
    ]
    alternate_cols = [col for col in alternate_cols if col in alternate_frame.columns]
    st.dataframe(alternate_frame[alternate_cols].head(12), hide_index=True, use_container_width=True)

if rejections:
    with st.expander("Rejected / filtered stocks - why they missed", expanded=not candidates):
        st.caption(
            "This shows the stocks Dave checked but did not place in the main slate. "
            "Most misses come from expensive contracts, no liquid option, weak evidence, or lower rank."
        )
        rejected_frame = pd.DataFrame(rejections)
        preferred_cols = [
            "Symbol", "Direction", "Status", "Confidence", "Price",
            "Premium / max loss", "Max allowed", "Why rejected", "Next move",
        ]
        shown_cols = [col for col in preferred_cols if col in rejected_frame.columns]
        st.dataframe(rejected_frame[shown_cols].head(40), hide_index=True, use_container_width=True)

errors = st.session_state.get("errors", [])
if errors:
    with st.expander("Data-source warnings"):
        st.write("\n".join(errors))

st.divider()
st.caption("Decision support only. Data can be incomplete, delayed or wrong. The tool never submits orders and cannot predict earnings surprises or breaking news.")
