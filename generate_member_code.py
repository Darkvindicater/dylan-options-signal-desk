from __future__ import annotations

import argparse
import hashlib
import hmac
import os
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).parent
SECRET_FILE = ROOT / "member_code_secret.txt"


def load_secret() -> str:
    secret = os.environ.get("ROTATING_ACCESS_SECRET", "").strip()
    if secret:
        return secret
    if SECRET_FILE.exists():
        secret = SECRET_FILE.read_text(encoding="utf-8").strip()
        if secret:
            return secret
    raise SystemExit(
        "Missing rotating secret. Add ROTATING_ACCESS_SECRET to the environment "
        "or create member_code_secret.txt next to this script."
    )


def month_key(months_ahead: int = 0) -> str:
    now = datetime.now().astimezone()
    year = now.year
    month = now.month + months_ahead
    while month > 12:
        month -= 12
        year += 1
    return f"{year:04d}{month:02d}"


def day_key(days_ahead: int = 0) -> str:
    return (datetime.now().astimezone() + timedelta(days=days_ahead)).strftime("%Y%m%d")


def member_code(email: str, secret: str, period_key: str) -> str:
    normalized_email = email.strip().lower()
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{normalized_email}|{period_key}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()
    return f"DD-{period_key}-{digest[:4]}-{digest[4:8]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate rotating Dylan Dave member access codes.")
    parser.add_argument("emails", nargs="+", help="Subscriber email address(es).")
    parser.add_argument("--period", choices=["monthly", "daily"], default="monthly")
    parser.add_argument("--ahead", type=int, default=0, help="Months/days ahead to generate. Default: current period.")
    args = parser.parse_args()

    secret = load_secret()
    period_key = month_key(args.ahead) if args.period == "monthly" else day_key(args.ahead)
    for email in args.emails:
        print(f"{email.strip().lower()}  {period_key}  {member_code(email, secret, period_key)}")


if __name__ == "__main__":
    main()
