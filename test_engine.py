import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from engine import SignalEngine


class EngineTests(unittest.TestCase):
    def test_bullish_score(self):
        config = {"account_size": 500, "max_risk_per_trade_pct": 8}
        engine = SignalEngine(config)
        data = {
            "price": 110, "ema9": 108, "ema21": 105, "sma50": 100, "rsi14": 62,
            "return_5d": .04, "return_20d": .10, "volume_ratio": 1.25,
        }
        score, details = engine.score(data, [{"sentiment": .4}])
        self.assertGreater(score, 0)
        self.assertGreater(details["trend"], 0)

    def test_confidence_can_reach_80_without_implying_certainty(self):
        self.assertEqual(SignalEngine.confidence(0), 50)
        self.assertGreaterEqual(SignalEngine.confidence(7), 80)
        self.assertLessEqual(SignalEngine.confidence(100), 90)

    def test_indicators(self):
        prices = pd.Series(range(1, 81), dtype=float)
        frame = pd.DataFrame({"Close": prices, "Volume": [2_000_000] * 80})
        result = SignalEngine.indicators(frame)
        self.assertEqual(result["price"], 80)
        self.assertGreater(result["ema9"], result["ema21"])

    def test_named_catalyst_required(self):
        found, label = SignalEngine.catalyst_check([{"title": "Company wins major government contract"}])
        self.assertTrue(found)
        self.assertIn("Contract", label)
        found, _ = SignalEngine.catalyst_check([{"title": "Company shares trade quietly"}])
        self.assertFalse(found)
        found, _ = SignalEngine.catalyst_check([{"title": "Price to earnings forward of Example Inc"}])
        self.assertFalse(found)

    def test_weinstein_stage_two(self):
        prices = pd.Series(range(1, 121), dtype=float)
        frame = pd.DataFrame({"Close": prices})
        self.assertTrue(SignalEngine.weinstein_stage(frame).startswith("Stage 2"))

    def test_account_scaled_stock_price(self):
        engine = SignalEngine({"account_size": 500, "minimum_stock_price": 10, "max_stock_price_per_account_dollar": .4})
        self.assertEqual(engine.maximum_stock_price(), 200)
        self.assertTrue(engine.stock_price_fits_account(150))
        self.assertFalse(engine.stock_price_fits_account(250))

    def test_grind_account_uses_lower_stock_price_ceiling(self):
        engine = SignalEngine({"account_size": 300, "minimum_stock_price": 5, "max_stock_price_per_account_dollar": .25})
        self.assertEqual(engine.maximum_stock_price(), 75)
        self.assertTrue(engine.stock_price_fits_account(50))
        self.assertFalse(engine.stock_price_fits_account(100))

    def test_acquisition_explanation_mentions_dilution(self):
        explanation = SignalEngine.explain_catalyst("Acquisition catalyst: Company to acquire target")
        self.assertIn("dilution", explanation)

    def test_trade_setup_default_holding_plan(self):
        plan = SignalEngine.holding_plan(
            "TRADE SETUP",
            {"days_to_expiry": 30},
            "Not available",
            68,
            False,
            False,
        )
        self.assertEqual(plan["suggested_hold"], "3-5 trading days after entry")

    def test_watchlist_has_no_entry_hold(self):
        plan = SignalEngine.holding_plan("WATCH", None, "Not available", 60, False, False)
        self.assertIn("No hold yet", plan["suggested_hold"])

    def test_relief_bounce_is_not_actionable_catalyst(self):
        quality = SignalEngine.move_quality(
            "PUT",
            {"volume_ratio": .9, "latest_volume_ratio": .4},
            pd.Series([-.04, .03]),
            [{"title": "Company expected to report earnings next week"}],
            "Earnings/results catalyst: Company expected to report earnings next week",
            "Not available",
        )
        self.assertEqual(quality["source_type"], "Relief bounce")
        self.assertFalse(quality["actionable_catalyst"])

    def test_material_news_with_volume_is_actionable(self):
        quality = SignalEngine.move_quality(
            "CALL",
            {"volume_ratio": 1.4, "latest_volume_ratio": 1.6},
            pd.Series([.01, .04]),
            [{"title": "Company beats estimates and raises guidance"}],
            "Earnings/results catalyst: Company beats estimates and raises guidance",
            "Not available",
        )
        self.assertTrue(quality["actionable_catalyst"])
        self.assertIn("News", quality["source_type"])

    def test_move_discovery_finds_relief_bounce(self):
        signal = SignalEngine.move_discovery_signal(
            pd.Series([100, 101, 100, 99, 100, 96, 99], dtype=float),
            pd.Series([1_000_000, 1_100_000, 900_000, 1_000_000, 950_000, 1_200_000, 700_000], dtype=float),
        )
        self.assertEqual(signal["pattern"], "relief_bounce")
        self.assertGreater(signal["score"], 0)

    def test_move_discovery_finds_failed_bounce(self):
        signal = SignalEngine.move_discovery_signal(
            pd.Series([100, 99, 100, 101, 100, 104, 100], dtype=float),
            pd.Series([1_000_000, 1_100_000, 900_000, 1_000_000, 950_000, 1_200_000, 1_400_000], dtype=float),
        )
        self.assertEqual(signal["pattern"], "failed_bounce")
        self.assertGreater(signal["score"], 0)

    def test_premarket_up_fakeout_confirms_put_bias(self):
        index = pd.to_datetime([
            "2026-07-13 04:00", "2026-07-13 09:20", "2026-07-13 09:25",
            "2026-07-13 09:30", "2026-07-13 09:35", "2026-07-13 09:40",
            "2026-07-13 09:45",
        ]).tz_localize("America/New_York")
        frame = pd.DataFrame({
            "Open": [10.00, 10.55, 10.60, 10.55, 10.45, 10.30, 10.20],
            "High": [10.05, 10.70, 10.68, 10.60, 10.50, 10.35, 10.25],
            "Low": [9.95, 10.50, 10.55, 10.40, 10.25, 10.15, 10.10],
            "Close": [10.00, 10.60, 10.62, 10.45, 10.30, 10.20, 10.15],
            "Volume": [1000, 1500, 1600, 5000, 6000, 7000, 8000],
        }, index=index)

        context = SignalEngine.interpret_premarket_open(frame, "PUT")

        self.assertEqual(context["trade_bias"], "PUT")
        self.assertEqual(context["gate"], "CONFIRMED")
        self.assertIn("fakeout", context["label"].lower())

    def test_premarket_detector_waits_before_first_15_minutes(self):
        index = pd.to_datetime([
            "2026-07-13 04:00", "2026-07-13 09:25",
            "2026-07-13 09:30", "2026-07-13 09:35",
        ]).tz_localize("America/New_York")
        frame = pd.DataFrame({
            "Open": [10.00, 10.40, 10.45, 10.50],
            "High": [10.05, 10.45, 10.55, 10.60],
            "Low": [9.95, 10.35, 10.40, 10.45],
            "Close": [10.00, 10.42, 10.50, 10.55],
            "Volume": [1000, 1500, 5000, 6000],
        }, index=index)

        context = SignalEngine.interpret_premarket_open(frame, "CALL")

        self.assertEqual(context["trade_bias"], "WAIT")
        self.assertEqual(context["gate"], "WAIT")
        self.assertIn("9:45", context["label"])

    def test_restaurant_theme_symbols_are_enabled(self):
        engine = SignalEngine({
            "theme_universes": {"Restaurants": ["BROS", "CMG"]},
            "enabled_theme_universes": ["Restaurants"],
        })
        self.assertEqual(engine.theme_universe_symbols(), ["BROS", "CMG"])
        self.assertEqual(engine.symbol_themes("BROS"), ["Restaurants"])

    def test_discovery_caps_theme_names_before_full_analysis(self):
        engine = SignalEngine({
            "watchlist": ["AAA"],
            "discovery_universe": [],
            "priority_symbols": ["CAG"],
            "theme_universes": {
                "Restaurants": ["BROS", "WING", "CMG"],
                "Retail": ["LEVI", "LULU"],
            },
            "enabled_theme_universes": ["Restaurants", "Retail"],
            "discovery_limit": 2,
            "move_discovery_limit": 2,
            "theme_discovery_limit": 2,
            "max_symbols_to_analyze": 5,
            "account_size": 250,
            "minimum_stock_price": 10,
            "max_stock_price_per_account_dollar": .4,
        })
        engine.top_us_symbols = lambda: []
        engine.news_discovery_symbols = lambda: ["NEWS1", "NEWS2"]

        def fake_download(symbols, **_kwargs):
            frames = {}
            close_sets = {
                "BROS": [40, 41, 42, 43, 44, 50],
                "WING": [80, 81, 80, 82, 81, 82],
                "CMG": [150, 151, 152, 153, 154, 155],
                "LEVI": [18, 18.5, 19, 19.5, 20, 23],
                "LULU": [300, 301, 302, 303, 304, 305],
            }
            for symbol in symbols:
                closes = close_sets.get(symbol, [30, 30.5, 31, 31.5, 32, 33])
                frames[symbol] = pd.DataFrame({
                    "Close": closes,
                    "Volume": [2_000_000] * len(closes),
                })
            return pd.concat(frames, axis=1)

        with patch("engine.yf.download", side_effect=fake_download):
            symbols = engine.discover_symbols()

        self.assertLessEqual(len(symbols), 5)
        self.assertIn("CAG", symbols)
        self.assertIn("BROS", symbols)
        self.assertIn("LEVI", symbols)
        self.assertNotIn("WING", symbols)

    def test_broad_discovery_pool_limits_downloaded_symbols(self):
        engine = SignalEngine({
            "watchlist": [],
            "discovery_universe": [],
            "priority_symbols": [],
            "theme_universes": {},
            "enabled_theme_universes": [],
            "discovery_limit": 3,
            "move_discovery_limit": 3,
            "theme_discovery_limit": 0,
            "broad_discovery_pool_size": 2,
            "max_symbols_to_analyze": 10,
            "account_size": 250,
            "minimum_stock_price": 10,
            "max_stock_price_per_account_dollar": .4,
        })
        engine.top_us_symbols = lambda: ["AAA", "BBB", "CCC"]
        engine.news_discovery_symbols = lambda: []
        downloaded = []

        def fake_download(symbols, **_kwargs):
            downloaded.extend(symbols)
            return pd.concat({
                symbol: pd.DataFrame({
                    "Close": [20, 21, 22, 23, 24, 25],
                    "Volume": [2_000_000] * 6,
                })
                for symbol in symbols
            }, axis=1)

        with patch("engine.yf.download", side_effect=fake_download):
            engine.discover_symbols()

        self.assertEqual(downloaded, ["AAA", "BBB"])

    def test_scan_main_list_requires_budget_qualified_contracts(self):
        engine = SignalEngine({
            "watchlist": ["CALLGOOD", "CALLEXP", "PUTGOOD", "PUTNONE"],
            "automatic_discovery": False,
            "account_size": 350,
            "max_risk_per_trade_pct": 20,
            "max_call_candidates": 3,
            "max_put_candidates": 3,
            "budget_qualified_main_list": True,
        })

        def fake_candidate(symbol, direction, option_cost):
            return SimpleNamespace(
                symbol=symbol,
                direction=direction,
                setup_status="MOVE WATCH",
                advantage_profile={"score": 80},
                a_plus_score=70,
                confidence=82,
                option=None if option_cost is None else {"estimated_cost_and_max_loss": option_cost},
            )

        fake_candidates = {
            "CALLGOOD": fake_candidate("CALLGOOD", "CALL", 65),
            "CALLEXP": fake_candidate("CALLEXP", "CALL", 800),
            "PUTGOOD": fake_candidate("PUTGOOD", "PUT", 55),
            "PUTNONE": fake_candidate("PUTNONE", "PUT", None),
        }
        engine.analyze = lambda symbol: fake_candidates[symbol]

        candidates, errors = engine.scan()

        self.assertEqual([candidate.symbol for candidate in candidates], ["CALLGOOD", "PUTGOOD"])
        self.assertTrue(any("Budget filter found" in error for error in errors))
        rejected = {row["Symbol"]: row["Why rejected"] for row in engine.rejection_report}
        self.assertIn("CALLEXP", rejected)
        self.assertIn("PUTNONE", rejected)
        self.assertIn("above the account cap", rejected["CALLEXP"])
        self.assertIn("No liquid near-the-money contract", rejected["PUTNONE"])

    def test_option_last_price_fallback_surfaces_robinhood_quote_check(self):
        expiry = (datetime.now(timezone.utc).date() + timedelta(days=21)).strftime("%Y-%m-%d")
        option_frame = pd.DataFrame({
            "contractSymbol": ["SOFI_FAKE_CALL"],
            "strike": [19.0],
            "lastPrice": [0.70],
            "bid": [0.0],
            "ask": [0.0],
            "openInterest": [6000],
            "volume": [1900],
            "impliedVolatility": [0.55],
        })
        fake_ticker = SimpleNamespace(
            options=[expiry],
            option_chain=lambda _expiry: SimpleNamespace(calls=option_frame, puts=option_frame),
        )
        engine = SignalEngine({
            "account_size": 350,
            "max_risk_per_trade_pct": 35,
            "option_days_min": 14,
            "option_days_max": 35,
            "preferred_contract_min": 10,
            "preferred_contract_max": 350,
            "minimum_option_volume": 100,
            "minimum_open_interest": 500,
            "budget_contract_fallback": True,
            "fallback_option_max_distance": 0.08,
            "fallback_option_max_spread_pct": 0.45,
            "fallback_minimum_option_volume": 10,
            "fallback_minimum_open_interest": 50,
            "option_last_price_fallback": True,
        })

        with patch("engine.yf.Ticker", return_value=fake_ticker):
            contract = engine.option_contract("SOFI", "CALL", 19.20)

        self.assertIsNotNone(contract)
        self.assertEqual(contract["quality_tier"], "Robinhood quote check")
        self.assertEqual(contract["estimated_cost_and_max_loss"], 70.0)
        self.assertIn("verify in Robinhood", contract["quote_status"])

    def test_failed_pop_becomes_put_fade_watch(self):
        config = {
            "account_size": 350,
            "max_risk_per_trade_pct": 35,
            "minimum_stock_price": 5,
            "max_stock_price_per_account_dollar": .25,
            "minimum_average_volume": 500000,
            "minimum_average_dollar_volume": 5000000,
            "minimum_confidence": 80,
            "watch_minimum_confidence": 52,
            "minimum_checklist_score": 8,
            "minimum_option_volume": 100,
            "minimum_open_interest": 500,
            "option_days_min": 14,
            "option_days_max": 35,
            "small_account_contract_ideal_min": 10,
            "small_account_contract_ideal_max": 350,
            "theme_universes": {},
            "enabled_theme_universes": [],
        }
        engine = SignalEngine(config)
        closes = [10.0] * 55 + [11.0, 10.55]
        frame = pd.DataFrame({
            "Close": closes,
            "Volume": [2_000_000] * len(closes),
        })
        engine.market_data = lambda _symbol: frame
        engine.indicators = lambda _frame: {
            "price": 10.55,
            "ema9": 10.30,
            "ema21": 10.70,
            "sma50": 11.00,
            "rsi14": 42.0,
            "return_5d": .02,
            "return_20d": -.08,
            "volume_ratio": .7,
            "latest_volume_ratio": .6,
            "avg_volume": 2_000_000,
            "recent_high": 11.20,
            "recent_low": 10.20,
        }
        engine.company_check = lambda _symbol: {
            "name": "Fake Co",
            "sector": "Financial Services",
            "industry": "Crypto",
            "business": "A test business.",
            "revenue_growth": None,
            "earnings_growth": None,
            "debt_to_equity": None,
        }
        engine.news = lambda _symbol, _name: [{"title": "Fake Co reports operational update", "sentiment": .1}]
        engine.catalyst_check = lambda _headlines: (True, "Operational catalyst")
        engine.score = lambda _data, _headlines: (-2.2, {
            "trend": -2.3,
            "momentum": -1.0,
            "rsi": -0.3,
            "volume": -0.2,
            "news_sentiment": .1,
        })
        engine.intraday_structure = lambda _symbol: {
            "box_top": 11.20,
            "box_bottom": 10.20,
            "last_15m_close": 10.55,
            "volume_ratio": .6,
            "breakout_direction": "NONE",
            "breakout_confirmed": False,
            "volume_confirmed": False,
            "failed_breakout_up": False,
            "failed_breakdown_down": False,
        }
        engine.option_contract = lambda _symbol, direction, _price: {
            "contract": "MARA_FAKE_PUT",
            "estimated_cost_and_max_loss": 61.0,
            "spread_pct": 999.0,
            "volume": 500,
            "open_interest": 1000,
            "days_to_expiry": 21,
            "estimated_delta": -.45 if direction == "PUT" else .45,
        }
        engine.earnings_date = lambda _symbol: "Not available"
        engine.relative_strength = lambda _frame, _direction: (False, -.02)
        engine.weinstein_stage = lambda _frame: "Stage 1 - base/transition"
        engine.market_context = lambda: {"condition": "bullish", "SPY": .04, "QQQ": .04}

        candidate = engine.analyze("MARA")

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.direction, "PUT")
        self.assertEqual(candidate.setup_status, "PUT FADE WATCH")
        self.assertIn("failed-bounce", candidate.thesis)

    def test_small_account_advantage_rewards_affordable_liquid_contract(self):
        engine = SignalEngine({
            "account_size": 250,
            "max_risk_per_trade_pct": 10,
            "minimum_stock_price": 10,
            "max_stock_price_per_account_dollar": .4,
            "minimum_average_volume": 500000,
            "minimum_average_dollar_volume": 5000000,
            "minimum_option_volume": 100,
            "minimum_open_interest": 500,
            "option_days_min": 14,
            "option_days_max": 35,
            "small_account_contract_ideal_min": 10,
            "small_account_contract_ideal_max": 35,
            "theme_universes": {"Restaurants": ["BROS"]},
            "enabled_theme_universes": ["Restaurants"],
        })
        profile = engine.advantage_profile(
            "BROS",
            {"price": 55, "avg_volume": 2_000_000},
            {
                "estimated_cost_and_max_loss": 20,
                "spread_pct": 12,
                "volume": 500,
                "open_interest": 1200,
                "days_to_expiry": 21,
            },
            {"actionable_catalyst": True, "source_type": "News + volume confirmed", "label": "Real catalyst"},
            {"Clean Darvas box / base / structure": True, "Exact pivotal point": True},
            {"breakout_confirmed": True, "volume_confirmed": True},
            "TRADE SETUP",
            True,
            False,
        )
        self.assertGreaterEqual(profile["score"], 80)
        self.assertEqual(profile["label"], "SMALL ACCOUNT EDGE")

    def test_historical_profile_detects_comeback_after_selloff(self):
        prices = pd.Series(
            [100, 95, 90, 85, 80, 78, 76, 74, 73, 72, 74, 76, 78, 80, 82, 84, 86, 88, 90, 92,
             94, 96, 98, 100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122, 124,
             126, 128, 130, 132, 134, 136, 138, 140, 142, 144, 146, 148, 150, 152,
             154, 156, 158, 160, 162, 164, 166, 168, 170, 172],
            dtype=float,
        )
        frame = pd.DataFrame({"Close": prices, "Volume": [2_000_000] * len(prices)})
        profile = SignalEngine.historical_profile(frame)
        self.assertIn(profile["trend_label"], {"Comeback after selloff", "Quality uptrend"})
        self.assertGreater(profile["six_month_return_pct"], 0)


if __name__ == "__main__":
    unittest.main()
