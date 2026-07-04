# Dylan Options Signal Desk

A local Robinhood-oriented decision-support dashboard that combines 102 core symbols with the live top 1,000 U.S.-listed stocks and returns up to four CALL or PUT candidates using Dylan's Options Trading Playbook V2.

It does not place orders or guarantee results. It may return fewer than four candidates when required playbook rules are missing.

## Open anytime on this computer

Double-click `Open Options Signal Desk.bat`. Keep the terminal window open while using the dashboard. Open `http://localhost:8501` if the browser does not open automatically.

## Install on another computer

Requires Python 3.10 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## How the scanner works

1. Loads the top 1,000 stocks by market capitalization from Nasdaq and merges them with the core list.
2. Pre-screens price movement, unusual volume, stock price and dollar liquidity.
3. Applies Lynch story, O'Neil evidence, Weinstein stage, Minervini leadership, Darvas structure, Livermore confirmation and Douglas discipline.
4. Checks SPY/QQQ context, company fundamentals, catalyst news, earnings timing and late-entry risk.
5. Requires 15-minute structure plus 5-minute breakout or breakdown and volume confirmation.
6. Selects affordable, liquid options and displays spread, IV and estimated Delta, Gamma, Theta and Vega.
7. Scores the Playbook V2 100-point decision sheet. Missing structural rules cannot be overridden by a high score.
8. Ranks up to four candidates and shows setup type, entry, invalidation, two targets and maximum premium risk.

## Before any Robinhood order

- Confirm that the exact stock and contract are tradable in your Robinhood account.
- Confirm the live stock price, option bid/ask, volume, open interest and Greeks.
- Read the original linked news stories and check earnings or scheduled events again.
- Use limit orders and never average down into a broken setup.
- Treat the full premium of a long option as at risk.

## Limitations

- Yahoo Finance, Google News RSS and Nasdaq public data are not exchange-grade feeds and can be delayed or unavailable.
- Headline sentiment can miss nuance, rumors and details absent from the title.
- Greeks are estimates derived from public data; verify every value in Robinhood.
- Confidence and A+ scores are evidence filters, not historical win probabilities.
- The system needs a documented 30-trade sample before its real-world process performance can be evaluated.
