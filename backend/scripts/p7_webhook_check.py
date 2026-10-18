"""
Phase 7 (M11): is the webhook wired up? Changes no order.

Run from backend/ with the server running and RAZORPAY_WEBHOOK_SECRET set in
your .env (the same value you typed into the Razorpay Dashboard):

    python -m scripts.p7_webhook_check
    python -m scripts.p7_webhook_check --url https://<your-tunnel>/api/payments/webhook

It sends three harmless requests and reports PASS / FAIL for each:

  1. no signature                       -> must be refused (400)
  2. a wrong signature                  -> must be refused (400)
  3. a correctly signed event for a Razorpay order that is not ours
                                        -> must be accepted (200) and ignored

(3) proves the route, the tunnel and the secret all agree, without touching
any real order. Only run it against a TEST-mode setup (a key starting
"rzp_test_"); it refuses otherwise. The secret is never printed.
"""

import argparse
import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.request

from app.core.config import settings

DEFAULT_URL = "http://localhost:8000/api/payments/webhook"


def post(url: str, body: bytes, headers: dict):
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")
    except urllib.error.URLError as err:
        return None, str(err.reason)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=DEFAULT_URL, help=f"webhook URL (default {DEFAULT_URL})")
    args = parser.parse_args(argv)

    secret = settings.RAZORPAY_WEBHOOK_SECRET.get_secret_value()
    if not secret:
        print("RAZORPAY_WEBHOOK_SECRET is empty in your .env - set it first.")
        return 2
    if not settings.RAZORPAY_TEST_MODE:
        print("Refusing to run: RAZORPAY_KEY_ID is not a TEST key (rzp_test_...).")
        return 2

    body = json.dumps({
        "entity": "event", "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_PROBE000000001", "order_id": "order_PROBE000000001", "amount": 100, "currency": "INR"}}},
    }).encode()
    good = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    event_id = "probe_" + hashlib.sha256(body).hexdigest()[:24]

    probes = [
        ("1. no signature is refused", {}, 400),
        ("2. wrong signature is refused", {"X-Razorpay-Signature": "0" * 64}, 400),
        ("3. signed event for an unknown order is accepted and ignored", {"X-Razorpay-Signature": good, "X-Razorpay-Event-Id": event_id}, 200),
    ]
    ok = True
    for label, headers, expected in probes:
        status, text = post(args.url, body, headers)
        if status is None:
            print(f"FAIL  {label}: could not reach {args.url} ({text})")
            return 1
        passed = status == expected
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'}  {label}  (HTTP {status}, expected {expected})")
        if not passed:
            print(f"      server said: {text[:200]}")
            if expected == 200 and status == 400:
                print("      -> the secret in .env differs from the one the server loaded, or a proxy altered the body.")
            if status == 404:
                print("      -> wrong path: it must end in /api/payments/webhook (and the router must be included in main.py).")
            if status == 503:
                print("      -> the server has no RAZORPAY_WEBHOOK_SECRET: restart it after editing .env.")
    print("\nWebhook wiring looks right." if ok else "\nWebhook wiring has a problem - see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
