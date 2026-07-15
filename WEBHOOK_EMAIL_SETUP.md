# Automatic Stripe customer emails

This setup sends the member access email automatically as soon as Stripe confirms a paid checkout.

## What it sends

The customer receives:

- A one-click member access link.
- Their backup member code.
- The subscriber email tied to the code.
- A reminder not to share the link/code.
- The educational-only risk notice.

## Recommended email provider

Use Resend first because it is simple:

1. Create a Resend account.
2. Create an API key.
3. Add a verified sender/domain if Resend requires it for public customers.

You can also use SMTP instead.

## Secrets needed

Use the same values as the Streamlit app for these:

```env
APP_PUBLIC_URL=https://dylan-dave-options-desk.streamlit.app
ROTATING_ACCESS_SECRET=the-same-secret-from-streamlit
MEMBER_PASS_SECRET=the-same-secret-or-a-new-private-secret
MEMBER_PASS_DAYS=35
ROTATING_ACCESS_PERIOD=monthly
SUBSCRIPTION_PRICE_LABEL=$24.99/month
SUPPORT_EMAIL=your_support_email@example.com
```

For Stripe:

```env
STRIPE_WEBHOOK_SECRET=whsec_from_stripe_webhook_endpoint
STRIPE_ALLOWED_PAYMENT_LINK_ID=plink_optional_guardrail
STRIPE_EXPECTED_AMOUNT_CENTS=2499
```

For Resend:

```env
RESEND_API_KEY=re_your_resend_key
MEMBER_EMAIL_FROM=Dylan Dave Options Desk <your_verified_sender@example.com>
```

Or SMTP:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
MEMBER_EMAIL_FROM=your_email@gmail.com
```

Do not commit any real secrets to GitHub.

## Deploy the webhook service

Streamlit Community Cloud runs the dashboard, but it is not the right place for Stripe webhook endpoints. Deploy `stripe_webhook_emailer.py` to a small backend host such as Render, Railway, Fly.io, or another server that gives you a public HTTPS URL.

Run command:

```bash
uvicorn stripe_webhook_emailer:app --host 0.0.0.0 --port $PORT
```

Health check:

```text
https://YOUR-WEBHOOK-SERVICE/
```

Stripe webhook endpoint:

```text
https://YOUR-WEBHOOK-SERVICE/stripe-webhook
```

## Stripe settings

In Stripe Dashboard:

1. Go to **Developers**.
2. Go to **Webhooks**.
3. Click **Add endpoint**.
4. Paste:

```text
https://YOUR-WEBHOOK-SERVICE/stripe-webhook
```

5. Select these events:

```text
checkout.session.completed
checkout.session.async_payment_succeeded
```

6. Save.
7. Copy the webhook signing secret that starts with `whsec_`.
8. Put that value into your webhook service environment as `STRIPE_WEBHOOK_SECRET`.

## Important note

This webhook sends the access email immediately after Stripe confirms payment. For a larger paid business, add a real customer database later so you can automatically disable access when a subscription is canceled, refunded, or unpaid.
