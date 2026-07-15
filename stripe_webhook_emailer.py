from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from urllib.parse import urlencode

import requests
import stripe
from fastapi import FastAPI, Header, HTTPException, Request


app = FastAPI(title="Dylan Dave Options Desk Stripe Webhook Emailer")

PROCESSED_EVENT_IDS: set[str] = set()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def month_key(months_back: int = 0) -> str:
    now = datetime.now().astimezone()
    year = now.year
    month = now.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return f"{year:04d}{month:02d}"


def rotating_period_keys(period: str, grace_periods: int) -> list[str]:
    period = period.strip().lower()
    grace_periods = max(0, min(grace_periods, 3))
    now = datetime.now().astimezone()
    if period == "daily":
        return [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(grace_periods + 1)]
    return [month_key(i) for i in range(grace_periods + 1)]


def rotating_member_code(email: str, secret: str, period_key: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{email.strip().lower()}|{period_key}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()
    return f"DD-{period_key}-{digest[:4]}-{digest[4:8]}"


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def sign_member_payload(payload_b64: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()


def create_member_pass_token(email: str) -> tuple[str, str]:
    secret = env("MEMBER_PASS_SECRET") or env("ROTATING_ACCESS_SECRET")
    if not secret:
        raise RuntimeError("Missing MEMBER_PASS_SECRET or ROTATING_ACCESS_SECRET")

    expires_at = datetime.now().astimezone() + timedelta(days=max(1, min(env_int("MEMBER_PASS_DAYS", 35), 370)))
    payload = {
        "v": 1,
        "kind": "dd_member_pass",
        "email": email.strip().lower(),
        "expires": int(expires_at.timestamp()),
    }
    payload_b64 = b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"DDPASS.{payload_b64}.{sign_member_payload(payload_b64, secret)}", expires_at.strftime("%Y-%m-%d")


def current_member_code_for_email(email: str) -> tuple[str, str]:
    secret = env("ROTATING_ACCESS_SECRET")
    if not secret:
        raise RuntimeError("Missing ROTATING_ACCESS_SECRET")

    period = env("ROTATING_ACCESS_PERIOD", "monthly")
    period_key = rotating_period_keys(period, 0)[0]
    return rotating_member_code(email, secret, period_key), period_key


def app_public_url() -> str:
    return env("APP_PUBLIC_URL", "https://dylan-dave-options-desk.streamlit.app").rstrip("/")


def member_pass_access_url(member_pass: str) -> str:
    return f"{app_public_url()}?{urlencode({'member_pass': member_pass})}"


def checkout_email(session: dict) -> str:
    customer_details = session.get("customer_details") or {}
    return str(
        customer_details.get("email")
        or session.get("customer_email")
        or session.get("receipt_email")
        or ""
    ).strip().lower()


def checkout_is_paid(session: dict) -> bool:
    status = str(session.get("status", "")).lower()
    payment_status = str(session.get("payment_status", "")).lower()
    return status == "complete" and payment_status in {"paid", "no_payment_required"}


def checkout_matches_guardrails(session: dict) -> bool:
    allowed_payment_link = env("STRIPE_ALLOWED_PAYMENT_LINK_ID")
    if allowed_payment_link and session.get("payment_link") and session.get("payment_link") != allowed_payment_link:
        return False

    expected_amount = env_int("STRIPE_EXPECTED_AMOUNT_CENTS", 0)
    if expected_amount and session.get("amount_total") is not None:
        return int(session["amount_total"]) == expected_amount
    return True


def build_email(email: str, code: str, period_key: str, access_url: str) -> tuple[str, str, str]:
    price_label = env("SUBSCRIPTION_PRICE_LABEL", "$24.99/month")
    support_email = env("SUPPORT_EMAIL")
    subject = "Your Dylan Dave Options Desk member access"
    text = (
        "Welcome to Dylan Dave Options Desk.\n\n"
        f"Subscription: {price_label}\n"
        f"Subscriber email: {email}\n\n"
        "Your one-click member access link:\n"
        f"{access_url}\n\n"
        "Backup member code:\n"
        f"{code}\n\n"
        f"Code period: {period_key}\n\n"
        "Use the access link or enter your subscriber email and backup code one time. "
        "After it unlocks, bookmark the unlocked page. Do not share your access link or code.\n\n"
        "Safety note: Dylan Dave Options Desk is educational only, not financial advice. "
        "Options are risky and you are responsible for your own decisions.\n"
    )
    if support_email:
        text += f"\nSupport: {support_email}\n"

    html = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.55; color: #111827;">
      <h2>Your Dylan Dave Options Desk access is ready</h2>
      <p>Welcome, <strong>{email}</strong>.</p>
      <p><a href="{access_url}" style="background:#4f46e5;color:white;padding:12px 18px;border-radius:8px;text-decoration:none;display:inline-block;">Open member desk</a></p>
      <p>If the button does not work, copy this link:</p>
      <p style="word-break:break-all;">{access_url}</p>
      <p><strong>Backup member code:</strong></p>
      <pre style="background:#f3f4f6;padding:12px;border-radius:8px;">{code}</pre>
      <p><strong>Code period:</strong> {period_key}</p>
      <p>Use the access link or enter your subscriber email and backup code one time. After it unlocks, bookmark the unlocked page.</p>
      <p><strong>Do not share your access link or code.</strong></p>
      <p style="font-size:13px;color:#4b5563;">Educational only. Not financial advice. Options involve substantial risk, including possible loss of 100% of premium.</p>
    </div>
    """
    return subject, text, html


def send_with_resend(to_email: str, subject: str, text: str, html: str) -> None:
    api_key = env("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("Missing RESEND_API_KEY")

    payload: dict[str, object] = {
        "from": env("MEMBER_EMAIL_FROM", "Dylan Dave Options Desk <onboarding@resend.dev>"),
        "to": [to_email],
        "subject": subject,
        "text": text,
        "html": html,
    }
    reply_to = env("SUPPORT_EMAIL")
    if reply_to:
        payload["reply_to"] = [reply_to]

    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    if not (200 <= response.status_code < 300):
        raise RuntimeError(f"Resend rejected email: {response.status_code} {response.text[:300]}")


def send_with_smtp(to_email: str, subject: str, text: str, html: str) -> None:
    host = env("SMTP_HOST")
    username = env("SMTP_USERNAME")
    password = env("SMTP_PASSWORD")
    from_email = env("MEMBER_EMAIL_FROM", username)
    if not (host and username and password and from_email):
        raise RuntimeError("SMTP email settings are incomplete")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_email
    reply_to = env("SUPPORT_EMAIL")
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP(host, env_int("SMTP_PORT", 587), timeout=20) as server:
        server.starttls(context=context)
        server.login(username, password)
        server.send_message(message)


def send_member_access_email(email: str) -> None:
    code, period_key = current_member_code_for_email(email)
    member_pass, _expires = create_member_pass_token(email)
    subject, text, html = build_email(email, code, period_key, member_pass_access_url(member_pass))

    if env("RESEND_API_KEY"):
        send_with_resend(email, subject, text, html)
        return
    send_with_smtp(email, subject, text, html)


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "dylan-dave-stripe-webhook-emailer"}


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(default="", alias="stripe-signature")) -> dict[str, object]:
    payload = await request.body()
    webhook_secret = env("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Missing STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, webhook_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Stripe webhook signature: {exc}") from exc

    event_id = str(event.get("id", ""))
    if event_id in PROCESSED_EVENT_IDS:
        return {"received": True, "duplicate": True}

    event_type = str(event.get("type", ""))
    if event_type not in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        return {"received": True, "ignored": event_type}

    session = event["data"]["object"]
    if not checkout_is_paid(session):
        return {"received": True, "ignored": "checkout not paid"}
    if not checkout_matches_guardrails(session):
        raise HTTPException(status_code=400, detail="Checkout session failed app guardrails")

    email = checkout_email(session)
    if not email:
        raise HTTPException(status_code=400, detail="Checkout session did not include an email")

    send_member_access_email(email)
    PROCESSED_EVENT_IDS.add(event_id)
    return {"received": True, "emailed": email}
