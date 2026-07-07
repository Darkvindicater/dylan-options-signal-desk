from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import feedparser
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


@dataclass
class Candidate:
    symbol: str
    direction: str
    confidence: int
    price: float
    score: float
    thesis: str
    catalysts: list[str]
    risks: list[str]
    entry_idea: str
    invalidation: str
    target_idea: str
    earnings: str
    option: dict[str, Any] | None
    signal_details: dict[str, float]
    headlines: list[dict[str, Any]]
    setup_status: str
    checklist: dict[str, bool]
    darvas: dict[str, Any]
    company: dict[str, Any]
    catalyst: str
    setup_type: str
    weinstein_stage: str
    market_context: str
    a_plus_score: int
    reversal_watch: bool
    extended_watch: bool
    catalyst_analysis: str
    holding_plan: dict[str, Any]
    move_quality: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class SignalEngine:
    """Transparent heuristic scanner. Confidence is a model score, not a forecast guarantee."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.sentiment = SentimentIntensityAnalyzer()
        self._market_cache: dict[str, Any] | None = None
        self._nasdaq_rows: list[dict[str, Any]] = []

    def top_us_symbols(self) -> list[str]:
        """Load the largest active U.S.-listed operating companies from Nasdaq."""
        requested = int(self.config.get("top_market_universe_size", 0))
        if requested <= 0:
            return []
        url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5000&offset=0&download=true"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        rows = response.json()["data"]["rows"]
        self._nasdaq_rows = rows
        excluded_name_terms = ("warrant", "rights", " units", "acquisition", "preferred")
        eligible = []
        for row in rows:
            symbol = str(row.get("symbol") or "").strip().upper().replace(".", "-")
            name = str(row.get("name") or "").lower()
            if not re.fullmatch(r"[A-Z][A-Z0-9-]{0,5}", symbol):
                continue
            if any(term in name for term in excluded_name_terms):
                continue
            try:
                market_cap = float(row.get("marketCap") or 0)
                last_price = float(str(row.get("lastsale") or "0").replace("$", "").replace(",", ""))
            except ValueError:
                continue
            if market_cap <= 0 or not self.stock_price_fits_account(last_price):
                continue
            eligible.append((market_cap, symbol))
        eligible.sort(reverse=True)
        return [symbol for _, symbol in eligible[:requested]]

    def news_discovery_symbols(self) -> list[str]:
        """Find catalyst names before price/volume pre-screening can discard them."""
        if not self._nasdaq_rows:
            self.top_us_symbols()
        query = quote_plus(
            "stock (earnings OR guidance OR FDA OR approval OR contract OR acquisition "
            "OR partnership OR upgrade OR downgrade OR forecast) when:3d"
        )
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        )
        raw_titles = [str(item.get("title", "")).lower() for item in feed.entries]
        titles = [re.sub(r"[^a-z0-9 ]+", " ", title) for title in raw_titles]
        matches: list[str] = []
        excluded = ("warrant", "rights", " units", "acquisition", "preferred")
        suffixes = {"inc", "incorporated", "corp", "corporation", "company", "co", "plc", "ltd", "limited", "holdings", "group"}
        for row in self._nasdaq_rows:
            symbol = str(row.get("symbol") or "").strip().upper().replace(".", "-")
            name = str(row.get("name") or "").lower()
            if any(term in name for term in excluded) or not re.fullmatch(r"[A-Z][A-Z0-9-]{0,5}", symbol):
                continue
            try:
                price = float(str(row.get("lastsale") or "0").replace("$", "").replace(",", ""))
                volume = int(str(row.get("volume") or "0").replace(",", ""))
            except ValueError:
                continue
            if price < self.config["minimum_stock_price"] or volume < 250_000:
                continue
            words = [word for word in re.sub(r"[^a-z0-9 ]+", " ", name).split() if word not in suffixes]
            company_key = " ".join(words[:2])
            tagged_symbol = re.compile(
                rf"(?:\${re.escape(symbol.lower())}\b|(?:nasdaq|nyse|amex)\s*[:\-]?\s*{re.escape(symbol.lower())}\b|\({re.escape(symbol.lower())}\))"
            )
            if any(
                (len(company_key) >= 6 and company_key in title) or tagged_symbol.search(raw)
                for title, raw in zip(titles, raw_titles)
            ):
                matches.append(symbol)
        return list(dict.fromkeys(matches))[: int(self.config.get("news_discovery_limit", 20))]

    @staticmethod
    def _series(frame: pd.DataFrame, name: str) -> pd.Series:
        series = frame[name]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        return pd.to_numeric(series, errors="coerce").dropna()

    def market_data(self, symbol: str) -> pd.DataFrame:
        frame = yf.download(symbol, period="6mo", interval="1d", auto_adjust=True, progress=False)
        if frame.empty or len(frame) < 55:
            raise ValueError("Not enough price history")
        return frame

    def maximum_stock_price(self) -> float:
        return max(
            float(self.config["minimum_stock_price"]),
            float(self.config["account_size"]) * float(self.config.get("max_stock_price_per_account_dollar", .4)),
        )

    def stock_price_fits_account(self, price: float) -> bool:
        return float(self.config["minimum_stock_price"]) <= price <= self.maximum_stock_price()

    @staticmethod
    def move_discovery_signal(close: pd.Series, volume: pd.Series) -> dict[str, Any]:
        """Find CAG-style bounce/fade stocks before full news analysis."""
        close = pd.to_numeric(close, errors="coerce").dropna()
        volume = pd.to_numeric(volume, errors="coerce").dropna()
        if len(close) < 6 or len(volume) < 6:
            return {"score": 0.0, "pattern": "none", "direction_hint": "NONE"}

        returns = close.pct_change().dropna()
        if len(returns) < 2:
            return {"score": 0.0, "pattern": "none", "direction_hint": "NONE"}

        latest = float(returns.iloc[-1])
        previous = float(returns.iloc[-2])
        five_day = float(close.iloc[-1] / close.iloc[-6] - 1)
        volume_ratio = float(volume.iloc[-1] / max(volume.tail(20).mean(), 1))
        closes_near_day_high_proxy = latest > 0 and close.iloc[-1] >= close.tail(3).max() * .995
        closes_near_day_low_proxy = latest < 0 and close.iloc[-1] <= close.tail(3).min() * 1.005

        score = 0.0
        pattern = "none"
        direction_hint = "NONE"
        if latest >= .015 and previous <= -.025:
            pattern = "relief_bounce"
            direction_hint = "CALL_HOLD_OR_PUT_REJECTION"
            score = abs(previous) * 140 + latest * 120 + min(volume_ratio, 3) * 8
            if volume_ratio < .8:
                score += 8  # weak-volume bounce can be a clean rejection watch
            if closes_near_day_high_proxy:
                score += 4
        elif latest <= -.015 and previous >= .025:
            pattern = "failed_bounce"
            direction_hint = "PUT_CONTINUATION_OR_CALL_REVERSAL"
            score = abs(previous) * 140 + abs(latest) * 120 + min(volume_ratio, 3) * 8
            if volume_ratio >= 1.0:
                score += 8
            if closes_near_day_low_proxy:
                score += 4
        elif abs(latest) >= .035 and volume_ratio >= 1.2:
            pattern = "high_volume_momentum"
            direction_hint = "CALL" if latest > 0 else "PUT"
            score = abs(latest) * 120 + min(volume_ratio, 3) * 12 + abs(five_day) * 30

        return {
            "score": round(score, 3),
            "pattern": pattern,
            "direction_hint": direction_hint,
            "latest_daily_move": round(latest * 100, 2),
            "previous_daily_move": round(previous * 100, 2),
            "five_day_move": round(five_day * 100, 2),
            "volume_vs_20d": round(volume_ratio, 2),
        }

    def discover_symbols(self) -> list[str]:
        """Quickly reduce a broad liquid universe before slower news/options analysis."""
        core = self.config.get("discovery_universe", self.config["watchlist"])
        try:
            broad = self.top_us_symbols()
        except Exception:
            broad = []
        universe = list(dict.fromkeys([*core, *broad]))
        limit = min(int(self.config.get("discovery_limit", 20)), len(universe))
        move_limit = min(int(self.config.get("move_discovery_limit", 20)), len(universe))
        try:
            ranked: list[tuple[float, str]] = []
            move_ranked: list[tuple[float, str]] = []
            for start in range(0, len(universe), 200):
                symbols = universe[start:start + 200]
                batch = yf.download(
                    symbols, period="1mo", interval="1d", auto_adjust=True,
                    progress=False, group_by="ticker", threads=True,
                )
                for symbol in symbols:
                    frame = batch[symbol] if isinstance(batch.columns, pd.MultiIndex) and symbol in batch.columns.get_level_values(0) else pd.DataFrame()
                    if frame.empty or len(frame.dropna(how="all")) < 6:
                        continue
                    close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
                    volume = pd.to_numeric(frame["Volume"], errors="coerce").dropna()
                    if len(close) < 6 or len(volume) < 6 or not self.stock_price_fits_account(float(close.iloc[-1])):
                        continue
                    move_5d = abs(close.iloc[-1] / close.iloc[-6] - 1)
                    volume_ratio = volume.iloc[-1] / max(volume.tail(20).mean(), 1)
                    dollar_volume = close.iloc[-1] * volume.tail(20).mean()
                    if dollar_volume < 20_000_000:
                        continue
                    move_signal = self.move_discovery_signal(close, volume)
                    if move_signal["score"] > 0:
                        move_ranked.append((float(move_signal["score"]), symbol))
                    ranked.append((move_5d * 4 + min(volume_ratio, 4) / 4, symbol))
            ranked.sort(reverse=True)
            move_ranked.sort(reverse=True)
            selected = [symbol for _, symbol in ranked[:limit]]
            move_names = [symbol for _, symbol in move_ranked[:move_limit]]
            try:
                news_names = self.news_discovery_symbols()
            except Exception:
                news_names = []
            priority = [*self.config.get("priority_symbols", []), *news_names, *move_names, *selected]
            return list(dict.fromkeys(priority))
        except Exception:
            return self.config["watchlist"]

    def news(self, symbol: str, company_name: str = "", limit: int = 10) -> list[dict[str, Any]]:
        subject = company_name or symbol
        query = quote_plus(f'"{subject}" stock when:7d')
        feed = feedparser.parse(f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en")
        items: list[dict[str, Any]] = []
        for item in feed.entries[:limit]:
            title = item.get("title", "")
            compound = self.sentiment.polarity_scores(title)["compound"]
            items.append({
                "title": title,
                "link": item.get("link", ""),
                "published": item.get("published", ""),
                "sentiment": round(compound, 3),
                "summary": re.sub(r"<[^>]+>", " ", str(item.get("summary", ""))).strip()[:500],
            })
        return items

    @staticmethod
    def explain_catalyst(catalyst: str) -> str:
        text = catalyst.lower()
        if "acquisition" in text or "acquire" in text:
            return "M&A can expand the business and market opportunity, but verify deal funding, shareholder dilution, regulatory approval, integration risk, and whether the first move already priced in the benefit."
        if "earnings" in text or "guidance" in text or "forecast" in text:
            return "Compare reported results and forward guidance with expectations. Revenue quality, margins, guidance changes, and the market's prior positioning matter more than a simple beat or miss."
        if "fda" in text or "approval" in text or "regulatory" in text:
            return "Regulatory news can reprice biotechnology quickly. Verify the official decision, indication, label, remaining trial risk, cash runway, and whether volatility already expanded too far."
        if "upgrade" in text or "downgrade" in text or "analyst" in text:
            return "Analyst actions matter most when estimates, assumptions, or price targets materially change and price/volume confirms that institutions agree."
        if "contract" in text or "partnership" in text:
            return "Verify contract size, duration, revenue timing, customer concentration, and whether the economics are material relative to the company's existing business."
        if "no named catalyst" in text:
            return "No verified event explains the move. Treat it as technical or sector flow and require stronger price confirmation before considering a trade."
        return "Verify the original source, timestamp, financial materiality, market expectations, and whether price and volume confirm the headline."

    def company_check(self, symbol: str) -> dict[str, Any]:
        try:
            info = yf.Ticker(symbol).info
        except Exception:
            info = {}
        summary = str(info.get("longBusinessSummary") or "")
        return {
            "name": info.get("shortName") or info.get("longName") or symbol,
            "sector": info.get("sector") or "Unknown",
            "industry": info.get("industry") or "Unknown",
            "business": summary[:420] + ("…" if len(summary) > 420 else ""),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "debt_to_equity": info.get("debtToEquity"),
        }

    @staticmethod
    def catalyst_check(headlines: list[dict[str, Any]]) -> tuple[bool, str]:
        keywords = {
            "earnings": "Earnings/results catalyst",
            "contract": "Contract catalyst",
            "government": "Government catalyst",
            "fda": "FDA/regulatory catalyst",
            "approval": "Approval catalyst",
            "launch": "Product-launch catalyst",
            "partnership": "Partnership catalyst",
            "partner": "Partnership catalyst",
            "acquisition": "Acquisition catalyst",
            "acquire": "Acquisition catalyst",
            "upgrade": "Analyst-upgrade catalyst",
            "downgrade": "Analyst-downgrade catalyst",
            "8-k": "SEC filing catalyst",
            "guidance": "Guidance catalyst",
            "forecast": "Forecast catalyst",
            "tariff": "Policy/industry catalyst",
            "rate cut": "Macro catalyst",
            "fomc": "Macro catalyst",
            "cpi": "Macro catalyst",
        }
        false_catalyst_phrases = (
            "price to earnings", "p/e ratio", "shares trade quietly", "stock price forecast",
            "forward of", "historical stock price", "technical analysis",
        )
        for headline in headlines:
            title = headline["title"].lower()
            if any(phrase in title for phrase in false_catalyst_phrases):
                continue
            for keyword, label in keywords.items():
                if keyword in title:
                    return True, f"{label}: {headline['title']}"
        return False, "No named catalyst detected in recent headlines."

    @staticmethod
    def intraday_structure(symbol: str) -> dict[str, Any]:
        fifteen = yf.download(symbol, period="10d", interval="15m", auto_adjust=True, progress=False)
        five = yf.download(symbol, period="5d", interval="5m", auto_adjust=True, progress=False)
        if fifteen.empty or five.empty or len(fifteen) < 45 or len(five) < 25:
            raise ValueError("Not enough intraday data for Darvas confirmation")
        high15 = SignalEngine._series(fifteen, "High")
        low15 = SignalEngine._series(fifteen, "Low")
        close15 = SignalEngine._series(fifteen, "Close")
        vol15 = SignalEngine._series(fifteen, "Volume")
        high5 = SignalEngine._series(five, "High")
        low5 = SignalEngine._series(five, "Low")
        close5 = SignalEngine._series(five, "Close")
        vol5 = SignalEngine._series(five, "Volume")
        box_top = float(high15.iloc[-43:-3].max())
        box_bottom = float(low15.iloc[-43:-3].min())
        last = float(close15.iloc[-1])
        volume_ratio = float(vol15.iloc[-1] / max(vol15.iloc[-21:-1].mean(), 1))
        call_15 = last > box_top
        put_15 = last < box_bottom
        call_5 = float(close5.iloc[-1]) > float(high5.iloc[-21:-1].max())
        put_5 = float(close5.iloc[-1]) < float(low5.iloc[-21:-1].min())
        failed_breakout_up = float(high5.tail(8).max()) > box_top and float(close5.iloc[-1]) < box_top
        failed_breakdown_down = float(low5.tail(8).min()) < box_bottom and float(close5.iloc[-1]) > box_bottom
        volume_confirmed = volume_ratio >= 1.2 and float(vol5.iloc[-1]) >= float(vol5.iloc[-21:-1].mean())
        direction = "CALL" if call_15 and call_5 else "PUT" if put_15 and put_5 else "NONE"
        return {
            "box_top": round(box_top, 2),
            "box_bottom": round(box_bottom, 2),
            "last_15m_close": round(last, 2),
            "volume_ratio": round(volume_ratio, 2),
            "breakout_direction": direction,
            "breakout_confirmed": direction != "NONE",
            "volume_confirmed": volume_confirmed,
            "failed_breakout_up": failed_breakout_up,
            "failed_breakdown_down": failed_breakdown_down,
        }

    @staticmethod
    def relative_strength(symbol_frame: pd.DataFrame, direction: str) -> tuple[bool, float]:
        spy = yf.download("SPY", period="1mo", interval="1d", auto_adjust=True, progress=False)
        stock_close = SignalEngine._series(symbol_frame, "Close")
        spy_close = SignalEngine._series(spy, "Close")
        stock_return = float(stock_close.pct_change(5).iloc[-1])
        spy_return = float(spy_close.pct_change(5).iloc[-1])
        relative = stock_return - spy_return
        return (relative > 0 if direction == "CALL" else relative < 0), relative

    @staticmethod
    def indicators(frame: pd.DataFrame) -> dict[str, float]:
        close = SignalEngine._series(frame, "Close")
        volume = SignalEngine._series(frame, "Volume")
        returns = close.pct_change()
        ema9 = close.ewm(span=9, adjust=False).mean().iloc[-1]
        ema21 = close.ewm(span=21, adjust=False).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        recent_high = close.tail(20).max()
        recent_low = close.tail(20).min()
        atr_proxy = returns.tail(20).std() * math.sqrt(252)
        return {
            "price": float(close.iloc[-1]),
            "ema9": float(ema9),
            "ema21": float(ema21),
            "sma50": float(sma50),
            "rsi14": float(rsi.iloc[-1]),
            "return_5d": float(close.pct_change(5).iloc[-1]),
            "return_20d": float(close.pct_change(20).iloc[-1]),
            "volume_ratio": float(volume.tail(5).mean() / max(volume.tail(30).mean(), 1)),
            "latest_volume_ratio": float(volume.iloc[-1] / max(volume.tail(30).mean(), 1)),
            "avg_volume": float(volume.tail(30).mean()),
            "recent_high": float(recent_high),
            "recent_low": float(recent_low),
            "annualized_volatility": float(atr_proxy),
        }

    def earnings_date(self, symbol: str) -> str:
        try:
            dates = yf.Ticker(symbol).get_earnings_dates(limit=4)
            if dates is None or dates.empty:
                return "Not available"
            now = pd.Timestamp.now(tz="UTC")
            index = pd.to_datetime(dates.index, utc=True)
            future = index[index >= now]
            return future.min().strftime("%Y-%m-%d") if len(future) else "No upcoming date found"
        except Exception:
            return "Not available"

    def score(self, data: dict[str, float], headlines: list[dict[str, Any]]) -> tuple[float, dict[str, float]]:
        sentiment = float(np.mean([h["sentiment"] for h in headlines])) if headlines else 0.0
        trend = 0.0
        trend += 1.0 if data["ema9"] > data["ema21"] else -1.0
        trend += 1.0 if data["price"] > data["sma50"] else -1.0
        momentum = float(np.clip(data["return_5d"] * 20 + data["return_20d"] * 8, -2, 2))
        rsi_component = float(np.clip((data["rsi14"] - 50) / 15, -1.5, 1.5))
        volume_confirmation = float(np.clip((data["volume_ratio"] - 1) * 2, -1, 1))
        news_component = float(np.clip(sentiment * 3, -1.5, 1.5))
        total = trend * 1.15 + momentum + rsi_component * 0.65 + volume_confirmation * 0.45 + news_component
        details = {
            "trend": round(trend * 1.15, 2),
            "momentum": round(momentum, 2),
            "rsi": round(rsi_component * 0.65, 2),
            "volume": round(volume_confirmation * 0.45, 2),
            "news_sentiment": round(news_component, 2),
        }
        return round(total, 3), details

    @staticmethod
    def confidence(score: float) -> int:
        # Calibrated display range deliberately capped: heuristic evidence is never certainty.
        return int(round(50 + 28 * (1 - math.exp(-abs(score) / 3.2))))

    @staticmethod
    def trading_days_until(date_text: str) -> int | None:
        try:
            if not date_text or date_text in {"Not available", "No upcoming date found"}:
                return None
            target = pd.Timestamp(date_text).date()
            today = datetime.now(timezone.utc).date()
            days = np.busday_count(today, target)
            return int(days) if days >= 0 else None
        except Exception:
            return None

    @staticmethod
    def holding_plan(
        setup_status: str,
        option: dict[str, Any] | None,
        earnings: str,
        confidence: int,
        reversal_watch: bool,
        extended_watch: bool,
    ) -> dict[str, Any]:
        """Create a practical clock for short swing option trades."""
        earnings_days = SignalEngine.trading_days_until(earnings)
        dte = int(option["days_to_expiry"]) if option and option.get("days_to_expiry") is not None else None

        if setup_status != "TRADE SETUP":
            return {
                "suggested_hold": "No hold yet - watch 1-2 trading days",
                "min_trading_days": 0,
                "max_trading_days": 2,
                "review_cadence": "Recheck after the first hour, into the close, and again premarket.",
                "exit_early_if": [
                    "The Darvas trigger never confirms with volume.",
                    "News fades or a better catalyst stock takes leadership.",
                    "For reversal watches, price keeps trending instead of rejecting the stretched move.",
                ],
                "rationale": "This is a watchlist idea, not an entry. Let the setup prove itself before starting the 3-5 day clock.",
            }

        min_days, max_days = 3, 5
        reasons = ["Default Dylan swing-options plan is 3-5 trading days after confirmed entry."]
        if dte is not None and dte <= 21:
            min_days, max_days = 1, 3
            reasons.append("Expiration is close, so theta decay makes the hold shorter.")
        if earnings_days is not None and earnings_days <= 7:
            min_days, max_days = 1, min(max_days, 3)
            reasons.append("Earnings are close; avoid holding a long option through the surprise unless that is intentional.")
        if confidence >= 72 and dte is not None and dte >= 25 and (earnings_days is None or earnings_days > 10):
            max_days = max(max_days, 7)
            reasons.append("Stronger evidence with enough DTE can earn a small runner window.")
        if reversal_watch or extended_watch:
            min_days, max_days = 1, 3
            reasons.append("The move is stretched/reversal-sensitive, so do not overstay without fresh confirmation.")

        return {
            "suggested_hold": f"{min_days}-{max_days} trading days after entry",
            "min_trading_days": min_days,
            "max_trading_days": max_days,
            "review_cadence": "Review every market close; if up fast on day 1, protect gains instead of hoping.",
            "exit_early_if": [
                "Underlying loses the Darvas entry/retest level or hits the chart stop.",
                "Contract loses about 35-50% of premium before the thesis improves.",
                "Target 1 hits quickly; consider taking partial profit and only letting a runner continue.",
                "Fresh news contradicts the catalyst or market/sector flow turns against the trade.",
            ],
            "rationale": " ".join(reasons),
        }

    @staticmethod
    def move_quality(
        direction: str,
        data: dict[str, float],
        daily_returns: pd.Series,
        headlines: list[dict[str, Any]],
        catalyst: str,
        earnings: str,
    ) -> dict[str, Any]:
        """Explain whether the move looks catalyst-backed or only a technical bounce/fade."""
        latest_return = float(daily_returns.iloc[-1]) if len(daily_returns) else 0.0
        previous_return = float(daily_returns.iloc[-2]) if len(daily_returns) >= 2 else 0.0
        latest_volume_ratio = float(data.get("latest_volume_ratio", data.get("volume_ratio", 1.0)))
        text = " ".join(str(headline.get("title", "")) for headline in headlines).lower()
        catalyst_text = catalyst.lower()
        earnings_days = SignalEngine.trading_days_until(earnings)

        flags: list[str] = []
        verify: list[str] = []
        source_type = "Technical / sector flow"
        label = "No strong source found yet"
        score = 45
        actionable_catalyst = False

        material_terms = (
            "reported", "beats", "beat estimates", "raises guidance", "raised guidance",
            "cuts guidance", "cut guidance", "wins contract", "contract award",
            "fda approval", "approved", "acquires", "acquisition", "merger",
            "strategic partnership", "upgrade", "downgrade",
        )
        pre_event_terms = (
            "will release", "to release", "ahead of", "expected to report",
            "earnings scheduled", "forecasters", "expectations ahead",
        )
        index_terms = ("index", "s&p 500", "smallcap", "rebalanc", "removed from")
        value_terms = ("looks cheap", "undervalued", "dividend yield", "defensive appeal")

        has_material_news = any(term in text or term in catalyst_text for term in material_terms)
        has_pre_event_news = any(term in text for term in pre_event_terms) or (
            earnings_days is not None and earnings_days <= 10 and "earnings" in text
        )
        has_index_flow = any(term in text for term in index_terms)
        has_value_discussion = any(term in text for term in value_terms)
        relief_bounce = latest_return >= 0.015 and previous_return <= -0.025
        failed_bounce = latest_return <= -0.015 and previous_return >= 0.025
        low_volume = latest_volume_ratio < 0.8
        high_volume = latest_volume_ratio >= 1.2

        if has_material_news and high_volume:
            source_type = "News + volume confirmed"
            label = "Real catalyst with volume confirmation"
            score = 80
            actionable_catalyst = True
            flags.append("Headline appears material and price is moving with above-baseline volume.")
        elif has_material_news:
            source_type = "News, volume not confirmed"
            label = "Real catalyst, but volume still needs confirmation"
            score = 65
            actionable_catalyst = True
            flags.append("Headline appears material, but volume is not yet strong enough for full confirmation.")
        elif relief_bounce:
            source_type = "Relief bounce"
            label = "Bounce after prior selloff - not fresh bullish news"
            score = 35
            flags.append(f"Latest daily move is {latest_return:+.1%} after a {previous_return:+.1%} prior-day drop.")
            verify.append("For CALLs, require hold above the bounce high with stronger volume.")
            verify.append("For PUTs, watch for rejection back under the prior close/low.")
        elif failed_bounce:
            source_type = "Failed bounce / downside reversal"
            label = "Down move after prior pop - possible put flow"
            score = 60
            actionable_catalyst = "downgrade" in text or "cuts guidance" in text or "cut guidance" in text
            flags.append(f"Latest daily move is {latest_return:+.1%} after a {previous_return:+.1%} prior-day pop.")
            verify.append("For PUTs, require price to stay below the failed breakout area.")
        elif has_pre_event_news:
            source_type = "Pre-earnings positioning"
            label = "Earnings are coming - positioning, not results yet"
            score = 50
            flags.append("Headlines are about upcoming expectations, not a reported beat/miss yet.")
            verify.append("Check whether analysts changed estimates or only repeated the earnings date.")
        elif has_index_flow:
            source_type = "Index / rebalance flow"
            label = "Possible index/rebalance flow - can fade quickly"
            score = 45
            flags.append("Index changes can cause forced buying/selling that may not reflect business improvement.")
            verify.append("Wait for normal-volume follow-through after index flow settles.")
        elif has_value_discussion:
            source_type = "Value / dividend discussion"
            label = "Value bounce story - needs chart confirmation"
            score = 45
            flags.append("Cheap valuation or dividend talk can create a bounce without changing the trend.")
            verify.append("Confirm institutions are actually buying with volume and relative strength.")

        if low_volume:
            score = min(score, 55)
            flags.append(f"Latest volume is only {latest_volume_ratio:.2f}x its 30-day baseline.")
        if direction == "CALL" and latest_return < 0:
            flags.append("Price action is not confirming the CALL direction today.")
        if direction == "PUT" and latest_return > 0:
            flags.append("Price action is bouncing against the PUT direction today; wait for rejection.")
        if not verify:
            verify.append("Verify the original headline source, timestamp, price reaction, and volume before entry.")

        return {
            "label": label,
            "source_type": source_type,
            "score": int(round(score)),
            "actionable_catalyst": actionable_catalyst,
            "latest_daily_move": round(latest_return * 100, 2),
            "previous_daily_move": round(previous_return * 100, 2),
            "latest_volume_vs_30d": round(latest_volume_ratio, 2),
            "flags": flags,
            "verify": verify,
        }

    def option_contract(self, symbol: str, direction: str, price: float) -> dict[str, Any] | None:
        ticker = yf.Ticker(symbol)
        today = datetime.now(timezone.utc).date()
        expiries = []
        for value in ticker.options:
            expiry = datetime.strptime(value, "%Y-%m-%d").date()
            days = (expiry - today).days
            if self.config["option_days_min"] <= days <= self.config["option_days_max"]:
                expiries.append((expiry, value))
        if not expiries:
            return None
        expiry, expiry_text = min(expiries)
        chain = ticker.option_chain(expiry_text)
        contracts = chain.calls.copy() if direction == "CALL" else chain.puts.copy()
        if contracts.empty:
            return None
        contracts["mid"] = (contracts["bid"].fillna(0) + contracts["ask"].fillna(0)) / 2
        contracts["distance"] = (contracts["strike"] - price).abs() / price
        max_cost = self.config["account_size"] * self.config["max_risk_per_trade_pct"] / 100
        liquid = contracts[
            (contracts["ask"] > 0)
            & (contracts["ask"] * 100 <= max_cost)
            & (contracts["distance"] <= 0.03)
            & (contracts["openInterest"].fillna(0) >= self.config["minimum_open_interest"])
            & (contracts["volume"].fillna(0) >= self.config["minimum_option_volume"])
        ].copy()
        if liquid.empty:
            return None
        liquid["spread_pct"] = (liquid["ask"] - liquid["bid"]) / liquid["ask"].replace(0, np.nan)
        liquid = liquid[
            (liquid["spread_pct"] <= 0.25)
            & (liquid["ask"] * 100 >= self.config["preferred_contract_min"])
            & (liquid["ask"] * 100 <= self.config["preferred_contract_max"])
        ]
        if liquid.empty:
            return None
        row = liquid.sort_values(["distance", "spread_pct"]).iloc[0]
        premium = float(row["ask"]) * 100
        strike = float(row["strike"])
        iv = max(float(row.get("impliedVolatility", 0) or 0), 0.0001)
        years = max((expiry - today).days / 365, 1 / 365)
        rate = 0.045
        d1 = (math.log(price / strike) + (rate + iv * iv / 2) * years) / (iv * math.sqrt(years))
        d2 = d1 - iv * math.sqrt(years)
        normal_cdf = lambda value: (1 + math.erf(value / math.sqrt(2))) / 2
        normal_pdf = math.exp(-(d1 * d1) / 2) / math.sqrt(2 * math.pi)
        delta = normal_cdf(d1) if direction == "CALL" else normal_cdf(d1) - 1
        gamma = normal_pdf / (price * iv * math.sqrt(years))
        theta_year = -(price * normal_pdf * iv) / (2 * math.sqrt(years))
        theta_year += (-rate * strike * math.exp(-rate * years) * normal_cdf(d2) if direction == "CALL"
                       else rate * strike * math.exp(-rate * years) * normal_cdf(-d2))
        vega = price * normal_pdf * math.sqrt(years) / 100
        scenarios = {}
        for move in (0.02, 0.05):
            scenario_price = price * (1 + move if direction == "CALL" else 1 - move)
            intrinsic = max(scenario_price - strike, 0) if direction == "CALL" else max(strike - scenario_price, 0)
            pnl = intrinsic * 100 - premium
            scenarios[f"underlying_{'up' if direction == 'CALL' else 'down'}_{int(move * 100)}pct_at_expiry"] = {
                "stock_price": round(scenario_price, 2),
                "estimated_contract_pnl": round(pnl, 2),
                "estimated_return_pct": round(pnl / premium * 100, 1),
            }
        return {
            "contract": row.get("contractSymbol", ""),
            "expiry": expiry_text,
            "days_to_expiry": (expiry - today).days,
            "strike": round(strike, 2),
            "bid": round(float(row["bid"]), 2),
            "ask": round(float(row["ask"]), 2),
            "estimated_cost_and_max_loss": round(premium, 2),
            "break_even_at_expiry": round(strike + premium / 100 if direction == "CALL" else strike - premium / 100, 2),
            "open_interest": int(row.get("openInterest", 0) or 0),
            "volume": int(row.get("volume", 0) or 0),
            "implied_volatility": round(float(row.get("impliedVolatility", 0)) * 100, 1),
            "spread_pct": round(float(row["spread_pct"]) * 100, 1),
            "estimated_delta": round(delta, 3),
            "estimated_gamma": round(gamma, 4),
            "estimated_theta_per_day": round(theta_year / 365, 3),
            "estimated_vega_per_iv_point": round(vega, 3),
            "expiration_scenarios": scenarios,
        }

    @staticmethod
    def weinstein_stage(frame: pd.DataFrame) -> str:
        close = SignalEngine._series(frame, "Close")
        sma50 = close.rolling(50).mean()
        price = float(close.iloc[-1])
        rising = float(sma50.iloc[-1]) > float(sma50.iloc[-11])
        if price > float(sma50.iloc[-1]) and rising:
            return "Stage 2 - advancing"
        if price < float(sma50.iloc[-1]) and not rising:
            return "Stage 4 - declining"
        if price <= float(sma50.iloc[-1]) and rising:
            return "Stage 1 - base/transition"
        return "Stage 3 - topping/transition"

    def market_context(self) -> dict[str, Any]:
        if self._market_cache is not None:
            return self._market_cache
        readings = {}
        for symbol in ("SPY", "QQQ"):
            frame = yf.download(symbol, period="3mo", interval="1d", auto_adjust=True, progress=False)
            close = self._series(frame, "Close")
            readings[symbol] = float(close.pct_change(20).iloc[-1])
        average = sum(readings.values()) / len(readings)
        condition = "bullish" if average > .02 else "bearish" if average < -.02 else "range-bound/mixed"
        self._market_cache = {"condition": condition, **readings}
        return self._market_cache

    def analyze(self, symbol: str) -> Candidate | None:
        frame = self.market_data(symbol)
        data = self.indicators(frame)
        if (
            not self.stock_price_fits_account(data["price"])
            or data["avg_volume"] < self.config["minimum_average_volume"]
            or data["price"] * data["avg_volume"] < self.config.get("minimum_average_dollar_volume", 0)
        ):
            return None
        company = self.company_check(symbol)
        headlines = self.news(symbol, company["name"])
        catalyst_exists, catalyst = self.catalyst_check(headlines)
        score, details = self.score(data, headlines)
        try:
            darvas = self.intraday_structure(symbol)
        except Exception:
            darvas = {"box_top": data["recent_high"], "box_bottom": data["recent_low"], "last_15m_close": data["price"],
                      "volume_ratio": data["volume_ratio"], "breakout_direction": "NONE",
                      "breakout_confirmed": False, "volume_confirmed": False,
                      "failed_breakout_up": False, "failed_breakdown_down": False}
        daily_returns = self._series(frame, "Close").pct_change().dropna()
        one_day_return = float(daily_returns.iloc[-1])
        recent_gap_up = float(daily_returns.tail(3).max())
        recent_gap_down = float(daily_returns.tail(3).min())
        overextended_up = recent_gap_up >= .08 or data["return_5d"] >= .15 or data["rsi14"] >= 80
        overextended_down = recent_gap_down <= -.08 or data["return_5d"] <= -.15 or data["rsi14"] <= 20
        reversal_watch = darvas["breakout_direction"] == "NONE" and (
            darvas.get("failed_breakout_up", False) or darvas.get("failed_breakdown_down", False)
        )
        extended_watch = darvas["breakout_direction"] == "NONE" and not reversal_watch and (
            overextended_up or overextended_down
        )
        direction = darvas["breakout_direction"] if darvas["breakout_direction"] != "NONE" else (
            "PUT" if darvas.get("failed_breakout_up", False) else
            "CALL" if darvas.get("failed_breakdown_down", False) else
            "CALL" if overextended_up else "PUT" if overextended_down else "CALL" if score > 0 else "PUT"
        )
        confidence = self.confidence(score)
        if confidence < self.config["minimum_confidence"]:
            return None
        option = self.option_contract(symbol, direction, data["price"])
        earnings = self.earnings_date(symbol)
        move_quality = self.move_quality(direction, data, daily_returns, headlines, catalyst, earnings)
        catalysts = []
        risks = []
        if details["trend"] * score > 0:
            catalysts.append("Short- and medium-term trend agree with the trade direction.")
        if details["momentum"] * score > 0:
            catalysts.append("Recent price momentum confirms the directional setup.")
        if details["news_sentiment"] * score > 0:
            catalysts.append("Recent headline sentiment supports the setup.")
        if data["volume_ratio"] > 1.1:
            catalysts.append("Recent volume is above its 30-day baseline.")
        if move_quality["actionable_catalyst"]:
            catalysts.append(f"Source-of-move check: {move_quality['label']}.")
        else:
            risks.append(f"Source-of-move warning: {move_quality['label']}.")
        if abs(details["news_sentiment"]) < 0.2:
            risks.append("Headlines provide little directional confirmation.")
        if data["volume_ratio"] < 0.9:
            risks.append("Move is occurring on below-baseline volume.")
        if data["rsi14"] > 70 or data["rsi14"] < 30:
            risks.append("RSI is stretched; reversal risk is elevated.")
        risks.append("Long options can lose 100% of premium through direction, volatility, or time decay.")
        relative_ok, relative_value = self.relative_strength(frame, direction)
        details["relative_vs_spy_5d"] = round(relative_value * 100, 2)
        stage = self.weinstein_stage(frame)
        market = self.market_context()
        stage_ok = (direction == "CALL" and stage.startswith("Stage 2")) or (
            direction == "PUT" and (stage.startswith("Stage 4") or stage.startswith("Stage 3"))
        )
        market_ok = market["condition"] == "range-bound/mixed" or (
            direction == "CALL" and market["condition"] == "bullish"
        ) or (direction == "PUT" and market["condition"] == "bearish")
        market_text = (
            f"{market['condition']} - SPY 20d {market['SPY']:+.1%}, "
            f"QQQ 20d {market['QQQ']:+.1%}; {'aligned' if market_ok else 'trade needs extra evidence'}"
        )
        story_exists = bool(company["business"]) and (
            company["revenue_growth"] is None or company["revenue_growth"] > 0 or abs(data["return_20d"]) > .03
        )
        not_late = max(abs(recent_gap_up), abs(recent_gap_down)) <= .08 and abs(data["return_5d"]) <= .15 and 20 < data["rsi14"] < 80
        option_liquid = option is not None
        risk_ready = darvas["box_top"] > darvas["box_bottom"]
        box_width = (darvas["box_top"] - darvas["box_bottom"]) / max(data["price"], 0.01)
        clean_structure = risk_ready and box_width <= .18
        fundamental_evidence = any(
            value is not None and value > 0
            for value in (company["revenue_growth"], company["earnings_growth"])
        )
        option_match = option_liquid and .25 <= abs(option["estimated_delta"]) <= .75
        checklist = {
            "Story / thesis quality": story_exists and not_late,
            "Fundamental / business evidence": fundamental_evidence,
            "Real current catalyst": catalyst_exists and move_quality["actionable_catalyst"],
            "Correct Weinstein stage": stage_ok,
            "Leadership / relative strength or weakness": relative_ok,
            "Clean Darvas box / base / structure": clean_structure,
            "Exact pivotal point": risk_ready,
            "Price + volume confirmation": darvas["breakout_confirmed"] and darvas["volume_confirmed"],
            "Option quality + thesis match": option_match,
            "Invalidation + targets + position risk": risk_ready and option_liquid,
        }
        checklist_score = sum(checklist.values())
        a_plus_score = checklist_score * 10
        required_core = (
            catalyst_exists
            and move_quality["actionable_catalyst"]
            and not_late
            and stage_ok
            and darvas["breakout_confirmed"]
            and darvas["volume_confirmed"]
        )
        move_watch = (
            checklist_score >= 5
            and (
                catalyst_exists
                or move_quality["source_type"] in {
                    "Relief bounce",
                    "Failed bounce / downside reversal",
                    "Pre-earnings positioning",
                    "Index / rebalance flow",
                    "Value / dividend discussion",
                }
            )
        )
        setup_status = "TRADE SETUP" if checklist_score >= self.config["minimum_checklist_score"] and required_core and option_liquid else (
            "WATCH" if checklist_score >= 6 else "MOVE WATCH" if move_watch else "SKIP"
        )
        if reversal_watch:
            setup_status = "PUT REVERSAL WATCH" if direction == "PUT" else "CALL REVERSAL WATCH"
        elif extended_watch:
            setup_status = "EXTENDED CALL WATCH" if direction == "CALL" else "EXTENDED PUT WATCH"
        bullish = direction == "CALL"
        setup_type = (f"Move-source watch - {move_quality['source_type']}; not an approved entry" if setup_status == "MOVE WATCH" else
            "Reversal watch - failed level, but not approved until confirmation" if reversal_watch else
            "Extended continuation watch - wait for a base, hold, or retest; do not chase" if extended_watch else
            "Setup 3 - Failed Story Breakdown PUT" if not bullish else
            "Setup 2 - Leader Continuation CALL" if stage.startswith("Stage 2") and relative_ok else
            "Setup 1 - Early Story Breakout CALL"
        )
        score_label = "bullish" if score > 0 else "bearish"
        thesis = (
            f"{symbol} has a {score_label} momentum/news composite score of {score:+.2f}. "
            f"Price is {'above' if data['price'] > data['sma50'] else 'below'} its 50-day average, "
            f"with RSI {data['rsi14']:.1f} and 5-day return {data['return_5d']:.1%}. "
            f"Weinstein classification: {stage}. Market: {market_text}. "
            f"Move source: {move_quality['label']} ({move_quality['score']}/100)."
        )
        if reversal_watch:
            thesis += (
                f" The prior move is overextended ({one_day_return:+.1%} one day, "
                f"{data['return_5d']:+.1%} five days), so the app is watching the opposite direction; "
                "this is observation only until price confirms reversal."
            )
        elif extended_watch:
            thesis += (
                f" The move is extended ({one_day_return:+.1%} one day, {data['return_5d']:+.1%} five days). "
                f"The largest recent gap was {max(abs(recent_gap_up), abs(recent_gap_down)):.1%}. "
                "Momentum still points the same way, but entry is blocked until a new base, hold, or retest forms."
            )
        if bullish:
            box_height = max(darvas["box_top"] - darvas["box_bottom"], data["price"] * .01)
            entry = f"Entry only after a 15m/5m hold or retest above Darvas top ${darvas['box_top']:.2f} with volume."
            invalidation = f"Chart stop: below Darvas top/retest, approximately ${max(darvas['box_bottom'], darvas['box_top'] - box_height * .25):.2f}."
            target = f"Underlying targets: ${darvas['box_top'] + box_height:.2f}, then ${darvas['box_top'] + box_height * 2:.2f}."
        else:
            box_height = max(darvas["box_top"] - darvas["box_bottom"], data["price"] * .01)
            entry = f"Entry only after a 15m/5m hold or retest below Darvas bottom ${darvas['box_bottom']:.2f} with volume."
            invalidation = f"Chart stop: above Darvas bottom/retest, approximately ${min(darvas['box_top'], darvas['box_bottom'] + box_height * .25):.2f}."
            target = f"Underlying targets: ${max(0, darvas['box_bottom'] - box_height):.2f}, then ${max(0, darvas['box_bottom'] - box_height * 2):.2f}."
        holding_plan = self.holding_plan(setup_status, option, earnings, confidence, reversal_watch, extended_watch)
        return Candidate(symbol, direction, confidence, data["price"], score, thesis, catalysts, risks,
                         entry, invalidation, target, earnings, option, details, headlines,
                         setup_status, checklist, darvas, company, catalyst, setup_type, stage,
                         market_text, a_plus_score, reversal_watch, extended_watch,
                         self.explain_catalyst(catalyst), holding_plan, move_quality)

    def scan(self) -> tuple[list[Candidate], list[str]]:
        candidates: list[Candidate] = []
        errors: list[str] = []
        symbols = self.discover_symbols() if self.config.get("automatic_discovery", False) else self.config["watchlist"]
        for symbol in symbols:
            try:
                candidate = self.analyze(symbol.upper().strip())
                # WATCH names may be surfaced without a contract so catalyst
                # stocks are visible before the entry and option gates are ready.
                if candidate and candidate.setup_status != "SKIP":
                    candidates.append(candidate)
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
        status_rank = {"TRADE SETUP": 4, "PUT REVERSAL WATCH": 3, "CALL REVERSAL WATCH": 3,
                       "EXTENDED CALL WATCH": 2, "EXTENDED PUT WATCH": 2, "MOVE WATCH": 2,
                       "WATCH": 1, "SKIP": 0}
        candidates.sort(key=lambda item: (status_rank[item.setup_status], item.a_plus_score, item.confidence), reverse=True)
        calls = [item for item in candidates if item.direction == "CALL"][: int(self.config.get("max_call_candidates", 3))]
        puts = [item for item in candidates if item.direction == "PUT"][: int(self.config.get("max_put_candidates", 3))]
        return [*calls, *puts], errors
