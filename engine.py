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
            if market_cap <= 0 or last_price < self.config["minimum_stock_price"]:
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

    def discover_symbols(self) -> list[str]:
        """Quickly reduce a broad liquid universe before slower news/options analysis."""
        core = self.config.get("discovery_universe", self.config["watchlist"])
        try:
            broad = self.top_us_symbols()
        except Exception:
            broad = []
        universe = list(dict.fromkeys([*core, *broad]))
        limit = min(int(self.config.get("discovery_limit", 20)), len(universe))
        try:
            ranked: list[tuple[float, str]] = []
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
                    if len(close) < 6 or len(volume) < 6 or close.iloc[-1] < self.config["minimum_stock_price"]:
                        continue
                    move_5d = abs(close.iloc[-1] / close.iloc[-6] - 1)
                    volume_ratio = volume.iloc[-1] / max(volume.tail(20).mean(), 1)
                    dollar_volume = close.iloc[-1] * volume.tail(20).mean()
                    if dollar_volume < 20_000_000:
                        continue
                    ranked.append((move_5d * 4 + min(volume_ratio, 4) / 4, symbol))
            ranked.sort(reverse=True)
            selected = [symbol for _, symbol in ranked[:limit]]
            try:
                news_names = self.news_discovery_symbols()
            except Exception:
                news_names = []
            priority = [*self.config.get("priority_symbols", []), *news_names, *selected]
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
            })
        return items

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
            data["price"] < self.config["minimum_stock_price"]
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
        if abs(details["news_sentiment"]) < 0.2:
            risks.append("Headlines provide little directional confirmation.")
        if data["volume_ratio"] < 0.9:
            risks.append("Move is occurring on below-baseline volume.")
        if data["rsi14"] > 70 or data["rsi14"] < 30:
            risks.append("RSI is stretched; reversal risk is elevated.")
        risks.append("Long options can lose 100% of premium through direction, volatility, or time decay.")
        option = self.option_contract(symbol, direction, data["price"])
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
            "Real current catalyst": catalyst_exists,
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
        required_core = catalyst_exists and not_late and stage_ok and darvas["breakout_confirmed"] and darvas["volume_confirmed"]
        setup_status = "TRADE SETUP" if checklist_score >= self.config["minimum_checklist_score"] and required_core and option_liquid else (
            "WATCH" if checklist_score >= 6 else "SKIP"
        )
        if reversal_watch:
            setup_status = "PUT REVERSAL WATCH" if direction == "PUT" else "CALL REVERSAL WATCH"
        elif extended_watch:
            setup_status = "EXTENDED CALL WATCH" if direction == "CALL" else "EXTENDED PUT WATCH"
        bullish = direction == "CALL"
        setup_type = ("Reversal watch - failed level, but not approved until confirmation" if reversal_watch else
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
            f"Weinstein classification: {stage}. Market: {market_text}."
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
        return Candidate(symbol, direction, confidence, data["price"], score, thesis, catalysts, risks,
                         entry, invalidation, target, self.earnings_date(symbol), option, details, headlines,
                         setup_status, checklist, darvas, company, catalyst, setup_type, stage,
                         market_text, a_plus_score, reversal_watch, extended_watch)

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
                       "EXTENDED CALL WATCH": 2, "EXTENDED PUT WATCH": 2, "WATCH": 1, "SKIP": 0}
        candidates.sort(key=lambda item: (status_rank[item.setup_status], item.a_plus_score, item.confidence), reverse=True)
        calls = [item for item in candidates if item.direction == "CALL"][: int(self.config.get("max_call_candidates", 3))]
        puts = [item for item in candidates if item.direction == "PUT"][: int(self.config.get("max_put_candidates", 3))]
        return [*calls, *puts], errors
