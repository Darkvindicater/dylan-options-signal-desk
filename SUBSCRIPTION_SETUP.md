# Subscription setup

The app now supports a simple paid-membership gate.

## What is already built

- A user agreement checkbox before anyone can use the desk.
- Optional subscription mode.
- A `$24.99/month` membership page.
- A Stripe payment button when you add a Stripe Payment Link.
- Automatic Stripe return unlock after a paid checkout.
- A private member access-code check using Streamlit secrets as a backup.
- A signed member pass after one successful unlock so customers do not type the code every time.
- Share-safe plain-link behavior: if someone shares the plain app URL, the new visitor still sees the agreement and paywall first.

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
STRIPE_SECRET_KEY = "sk_live_your_private_stripe_secret_key"
STRIPE_PREFILLED_PROMO_CODE = ""
MEMBER_PASS_DAYS = "35"
SUPPORT_EMAIL = "your_support_email@example.com"
```

9. Save secrets and reboot the app if Streamlit does not restart automatically.

## Automatic unlock after payment

This is the no-manual-sending setup.

1. In Stripe, open your Payment Link.
2. Find the setting for what happens after payment.
3. Choose redirect customers back to your own website.
4. Use this redirect URL:

```text
https://dylan-dave-options-desk.streamlit.app/?session_id={CHECKOUT_SESSION_ID}
```

5. In Streamlit secrets, add your private Stripe secret key:

```toml
STRIPE_SECRET_KEY = "sk_live_your_private_stripe_secret_key"
```

When a customer pays, Stripe sends them back to the app with their Checkout Session ID. The app verifies that session with Stripe, unlocks their browser, creates a signed member pass, and shows them their current monthly member code as a backup.

Never commit or share `STRIPE_SECRET_KEY`.

Optional tighter guardrails:

```toml
STRIPE_ALLOWED_PAYMENT_LINK_ID = "plink_your_payment_link_id"
STRIPE_EXPECTED_AMOUNT_CENTS = "2499"
```

These are optional. They prevent another paid checkout session from the same Stripe account from unlocking this app by accident.

## Promo codes

Stripe promo codes are discount codes, not app access codes.

If you want the Subscribe button to prefill a Stripe promo code automatically, create an active coupon/promotion code in Stripe and then add this in Streamlit secrets:

```toml
STRIPE_PREFILLED_PROMO_CODE = "YOURCODE"
```

If a promo code does not work at checkout, check Stripe first:

- The Payment Link must allow promotion codes.
- The code must be an active Stripe **promotion code**, not only a coupon.
- The code must apply to the subscription/product being sold.
- The code cannot be expired, over its redemption limit, restricted to another customer, or blocked by a first-time-order rule.
- App member codes such as `DD-202607-XXXX-XXXX` are not Stripe promo codes.

## Backup access codes

The rotating-code version is still available as a backup. The customer only needs to use it once on their browser. After the first successful unlock, the app creates a signed member pass and puts it in the page URL so refreshing/reopening that page does not require the code again.

1. Customer pays through Stripe.
2. The app should unlock automatically after Stripe redirects them back.
3. If automatic unlock fails, you can generate their monthly code using their subscriber email.
4. Send them that email-specific monthly code one time.
5. They enter their email and code once.
6. The app saves a signed member pass for that browser for `MEMBER_PASS_DAYS`.

Generate a code locally:

```powershell
.venv\Scripts\python.exe generate_member_code.py customer@email.com
```

Generate next month's code:

```powershell
.venv\Scripts\python.exe generate_member_code.py customer@email.com --ahead 1
```

Sharing the plain app link does **not** unlock the app for someone else because Streamlit session state is per visitor/session. However, a subscriber can still share their email/code pair or their saved member-pass URL. To reduce that risk:

- Codes are tied to subscriber email.
- Codes rotate every month by default.
- After one good unlock, the subscriber gets a signed member pass so they do not keep typing the code.
- The signed member pass expires after `MEMBER_PASS_DAYS`, which defaults to 35 days.
- Tell subscribers to bookmark their saved-pass URL but not share it.
- Use `ROTATING_ACCESS_PERIOD = "daily"` only if you want daily codes, which is more work.
- Keep `ROTATING_ACCESS_SECRET` private and never commit it to GitHub.
- Tell subscribers not to share codes in the membership terms.

This setup removes repeated code entry for the same browser. For a bigger business, upgrade later to Stripe webhooks + a subscriber database so access can stay synced automatically when a card fails, a subscription is canceled, or a refund happens.

## Legal note

The in-app agreement is protective language, not a guaranteed shield from lawsuits. Before charging real subscribers, have a licensed attorney review the Terms of Service, disclaimer, refund policy, privacy policy, and subscription cancellation language.
