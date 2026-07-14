# Subscription setup

The app now supports a simple paid-membership gate.

## What is already built

- A user agreement checkbox before anyone can use the desk.
- Optional subscription mode.
- A `$24.99/month` membership page.
- A Stripe payment button when you add a Stripe Payment Link.
- A private member access-code check using Streamlit secrets.

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
STRIPE_PAYMENT_LINK = "https://buy.stripe.com/YOUR_PAYMENT_LINK"
ACCESS_CODES = "DAVE-MEMBER-001,DAVE-MEMBER-002,DAVE-MEMBER-003"
```

9. Save secrets and reboot the app if Streamlit does not restart automatically.

## How to use access codes

The simple version is manual:

1. Customer pays through Stripe.
2. You confirm payment in Stripe.
3. You send them one access code.
4. If someone cancels, remove or rotate that code in Streamlit secrets.

This is easy to launch but not fully automated. For a bigger business, upgrade later to Stripe Checkout + webhooks + a subscriber database.

## Legal note

The in-app agreement is protective language, not a guaranteed shield from lawsuits. Before charging real subscribers, have a licensed attorney review the Terms of Service, disclaimer, refund policy, privacy policy, and subscription cancellation language.
