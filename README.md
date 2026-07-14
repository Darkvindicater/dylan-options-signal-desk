# Dylan Options Signal Desk

A Streamlit decision-support dashboard for studying Robinhood-style option setups. It combines Dylan's watchlist, theme lanes, recent news, public price data, earnings context, and affordable-contract filters to return a balanced CALL/PUT watch slate.

It does not place orders, provide personalized financial advice, claim financial-regulator approval, or guarantee results. Users must do their own research and verify every setup before risking money. It may return fewer candidates when required playbook rules are missing or the option premium breaks the configured account risk cap.

## Open anytime on this computer

Double-click `Open Options Signal Desk.bat`. Open `http://localhost:8502` if the browser does not open automatically.

## Install on another computer

Requires Python 3.10 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Make it public

The app is prepared for Streamlit Community Cloud deployment. See `DEPLOYMENT.md`.

Short version:

1. Push this folder to a GitHub repository.
2. Go to `https://share.streamlit.io/`.
3. Connect GitHub and choose the repository.
4. Set the main file to `app.py`.
5. Deploy.

Do not upload `.venv/`, logs, cache folders, or `.streamlit/secrets.toml`.

## Paid subscription mode

The app includes an optional membership gate for a `$24.99/month` Stripe subscription and a user agreement screen before access. See `SUBSCRIPTION_SETUP.md`.

Short version:

1. Create a recurring `$24.99/month` Stripe Payment Link.
2. Add the payment link and member access codes in Streamlit secrets.
3. Set `SUBSCRIPTION_ENABLED = "true"`.

Never commit payment links, access codes, API keys, or `.streamlit/secrets.toml` to GitHub.

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
