"""Normalize an already-authenticated provider event and forward a signed event.
The operator/provider receiver must verify native webhook authentication first.
Never point a provider's unsigned payload directly at the generic ingestion API.
"""

import argparse, hashlib, hmac, json, os, time
from datetime import datetime, timezone
from urllib.request import Request, urlopen


from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.provider_events import normalize


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--provider", choices=["postmark", "sendgrid"], required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--url", required=True)
    args = p.parse_args()
    if not args.url.startswith("https://"):
        raise SystemExit("An HTTPS ingestion URL is required")
    secret = os.environ.get("DELIVERY_WEBHOOK_SECRET")
    if not secret:
        raise SystemExit("Set DELIVERY_WEBHOOK_SECRET securely")
    with open(args.input) as file:
        data = json.load(file)
    for event in data if isinstance(data, list) else [data]:
        raw = json.dumps(
            normalize(args.provider, event, args.domain), separators=(",", ":")
        ).encode()
        stamp = str(int(time.time()))
        signature = hmac.new(
            secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        request = Request(
            args.url,
            data=raw,
            headers={
                "Content-Type": "application/json",
                "X-Event-Timestamp": stamp,
                "X-Event-Signature": signature,
            },
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
            print("Event accepted; duplicate:", bool(result.get("duplicate")))


if __name__ == "__main__":
    main()
