# Subscription setup

The app now supports a simple paid-membership gate.

## What is already built

- A user agreement checkbox before anyone can use the desk.
- Optional subscription mode.
- A `$24.99/month` membership page.
- A Stripe payment button when you add a Stripe Payment Link.
- A private member access-code check using Streamlit secrets.
- Share-safe link behavior: if someone shares the app URL, the new visitor still sees the agreement and paywall first.

## Turn on $24.99/month payments

1. Create or log in to a Stripe account.
2. In Stripe, create a product named `Dylan Dave Options Desk`.
3. Create a recurring monthly price of `$24.99`.
4. Create a Stripe Payment Link for that recurring subscription.
5. Copy the payment link.
6. In Streamlit Community Cloud, open the app settings.
7. Go to **Secrets**.
8. Add:

```toml
SUBSCRIPTION_ENABLED = "true"
SUBSCRIPTION_PRICE_LABEL = "$24.99/month"
STRIPE_PAYMENT_LINK = "https://buy.stripe.com/YOUR_PAYMENT_LINK"
ACCESS_CODES = ""
ROTATING_ACCESS_SECRET = "a-long-random-private-secret"
ROTATING_ACCESS_PERIOD = "monthly"
ROTATING_ACCESS_GRACE_PERIODS = "0"
SUPPORT_EMAIL = "your_support_email@example.com"
```

9. Save secrets and reboot the app if Streamlit does not restart automatically.

## How to use access codes

The simple rotating-code version is still manual after payment, but the code refreshes automatically by billing period:

1. Customer pays through Stripe.
2. You confirm payment in Stripe.
3. You generate their monthly code using their subscriber email.
4. You send them that email-specific monthly code.
5. Next month, the old monthly code stops working and you generate the new one after renewal.

Generate a code locally:

```powershell
.venv\Scripts\python.exe generate_member_code.py customer@email.com
```

Generate next month's code:

```powershell
.venv\Scripts\python.exe generate_member_code.py customer@email.com --ahead 1
```

Sharing the app link does **not** unlock the app for someone else because Streamlit session state is per visitor/session. However, a subscriber can still share their email/code pair. To reduce that risk:

- Codes are tied to subscriber email.
- Codes rotate every month by default.
- Use `ROTATING_ACCESS_PERIOD = "daily"` only if you want daily codes, which is more work.
- Keep `ROTATING_ACCESS_SECRET` private and never commit it to GitHub.
- Tell subscribers not to share codes in the membership terms.

This is easy to launch but not fully automated. For a bigger business, upgrade later to Stripe Checkout + webhooks + a subscriber database so access is tied to a paid Stripe customer instead of a manual code.

## Legal note

The in-app agreement is protective language, not a guaranteed shield from lawsuits. Before charging real subscribers, have a licensed attorney review the Terms of Service, disclaimer, refund policy, privacy policy, and subscription cancellation language.
