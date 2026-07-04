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

    def test_weinstein_stage_two(self):
        prices = pd.Series(range(1, 121), dtype=float)
        frame = pd.DataFrame({"Close": prices})
        self.assertTrue(SignalEngine.weinstein_stage(frame).startswith("Stage 2"))


if __name__ == "__main__":
    unittest.main()
