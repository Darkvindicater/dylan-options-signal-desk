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
ACCESS_CODES = "DAVE-MEMBER-001,DAVE-MEMBER-002,DAVE-MEMBER-003"
SUPPORT_EMAIL = "your_support_email@example.com"
```

9. Save secrets and reboot the app if Streamlit does not restart automatically.

## How to use access codes

The simple version is manual:

1. Customer pays through Stripe.
2. You confirm payment in Stripe.
3. You send them one access code.
4. If someone cancels, remove or rotate that code in Streamlit secrets.

Sharing the app link does **not** unlock the app for someone else because Streamlit session state is per visitor/session. However, a subscriber can still share their access code. To reduce that risk:

- Create one code per subscriber.
- Remove canceled/refunded subscriber codes.
- Rotate codes if one gets shared.
- Tell subscribers not to share codes in the membership terms.

This is easy to launch but not fully automated. For a bigger business, upgrade later to Stripe Checkout + webhooks + a subscriber database so access is tied to a paid Stripe customer instead of a manual code.

## Legal note

The in-app agreement is protective language, not a guaranteed shield from lawsuits. Before charging real subscribers, have a licensed attorney review the Terms of Service, disclaimer, refund policy, privacy policy, and subscription cancellation language.
