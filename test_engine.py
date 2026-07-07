import unittest

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


if __name__ == "__main__":
    unittest.main()
