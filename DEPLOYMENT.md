# Public deployment guide

This project is ready to deploy as a public Streamlit app.

## Recommended public host

Use Streamlit Community Cloud because this is a Streamlit dashboard and the app already has the normal deploy files:

- `app.py`
- `requirements.txt`
- `.streamlit/config.toml`
- `config.json`
- `engine.py`

Official Streamlit docs: <https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app>

## Before publishing

1. Do not upload `.venv/`, `__pycache__/`, `.pytest_cache/`, or log files.
2. Do not commit `.streamlit/secrets.toml` if you add API keys later.
3. Keep the public disclaimer visible in the app.
4. Remember that public visitors will share the same free public data sources, so heavy scans can be slow or rate-limited.

## Deploy steps

1. Create or open a GitHub repository for the app.
2. Upload/push the project files from this folder.
3. Go to <https://share.streamlit.io/> or <https://streamlit.io/cloud>.
4. Sign in with GitHub.
5. Click **New app**.
6. Choose the repository and branch.
7. Set the main file path to `app.py`.
8. Click **Deploy**.

If Streamlit asks for secrets, leave it blank for the current version. This app currently uses public data sources and does not need an API key.

## Public safety note

This app is educational decision support only. It does not place trades, does not provide personalized financial advice, and does not guarantee that any option signal will profit. Every visitor must verify live quotes, liquidity, bid/ask spread, earnings dates, and tradability in their own brokerage account before doing anything.
