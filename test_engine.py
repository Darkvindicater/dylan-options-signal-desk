import unittest
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
