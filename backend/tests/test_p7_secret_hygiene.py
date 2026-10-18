"""
Phase 7 / Milestone 10: secrets stay on the server.

Static checks over the code and the published API (no database needed):
no Razorpay credential is written into source, `.env.example` holds
placeholders only, no response model can carry a secret or a signature, and no
log call is handed one. (The behavioural side - responses and log lines of real
journeys never containing a secret - is in test_p7_end_to_end.py.)
"""

import ast
import re
import unittest
from pathlib import Path

from fastapi import FastAPI

from app.api import orders as orders_api
from app.api import payments as payments_api

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND / "app"
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
SENSITIVE = re.compile(r"secret|signature|password|passwd|token|credential|authorization", re.I)


def python_files():
    return sorted(p for p in APP.rglob("*.py") if "__pycache__" not in p.parts)


class SourceTests(unittest.TestCase):
    def test_no_razorpay_key_is_written_into_the_code(self):
        # "rzp_test_xxxxxxxx" in a docstring or an error message is a placeholder, not a key
        pattern = re.compile(r"rzp_(live|test)_(?!x+\b)[A-Za-z0-9]{8,}")
        hits = [str(p.relative_to(BACKEND)) for p in python_files() if pattern.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(hits, [])

    def test_no_secret_setting_is_given_a_literal_value_in_the_code(self):
        # an annotation like `RAZORPAY_KEY_SECRET: Optional[SecretStr] = None` is fine; a string is not
        pattern = re.compile(r"""(RAZORPAY_\w*SECRET\w*|webhook_secret|key_secret)\s*(:[^=\n]+)?=\s*["'][^"']+["']""", re.I)
        hits = []
        for p in python_files():
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{p.relative_to(BACKEND)}:{n}")
        self.assertEqual(hits, [])

    def test_log_calls_are_never_given_a_secret_or_a_signature(self):
        offenders = []
        for path in python_files():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHODS):
                    continue
                owner = node.func.value
                if not (isinstance(owner, ast.Name) and owner.id in {"logger", "logging", "log"}):
                    continue
                for arg in node.args[1:] + [k.value for k in node.keywords]:  # args[0] is the message template
                    names = [n.id for n in ast.walk(arg) if isinstance(n, ast.Name)] + [n.attr for n in ast.walk(arg) if isinstance(n, ast.Attribute)]
                    bad = [n for n in names if SENSITIVE.search(n)]
                    if bad:
                        offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno} logs {bad}")
        self.assertEqual(offenders, [])


class EnvExampleTests(unittest.TestCase):
    def setUp(self):
        self.text = (BACKEND / ".env.example").read_text(encoding="utf-8")

    def values(self):
        out = {}
        for line in self.text.splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                out[key.strip()] = value.strip()
        return out

    def test_razorpay_credentials_are_blank_placeholders(self):
        values = self.values()
        for name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"):
            self.assertEqual(values.get(name), "", f"{name} must be present and empty in .env.example")
        self.assertNotRegex(self.text, r"rzp_(live|test)_[A-Za-z0-9]{8,}")

    def test_it_tells_the_developer_to_use_test_mode_and_to_keep_secrets_server_side(self):
        self.assertIn("TEST MODE", self.text)
        self.assertRegex(self.text, r"server-only")

    def test_the_documented_webhook_url_is_the_real_route_and_lists_the_handled_events(self):
        routes = {r.path for r in payments_api.router.routes}
        self.assertIn("/api/payments/webhook", routes)
        self.assertIn("/api/payments/webhook", self.text)
        self.assertNotIn("/razorpay/webhook", self.text)
        from app.services.razorpay_webhook import HANDLED_EVENTS

        for event in HANDLED_EVENTS:
            self.assertIn(event, self.text.replace("\n# ", " "), f"{event} is handled but not listed in .env.example")


class PublishedApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(orders_api.router)
        app.include_router(payments_api.router)
        self.schemas = app.openapi()["components"]["schemas"]

    def test_nothing_the_api_publishes_has_a_secret_field(self):
        offenders = [(name, prop) for name, schema in self.schemas.items()
                     for prop in schema.get("properties", {}) if re.search(r"secret|password", prop, re.I)]
        self.assertEqual(offenders, [])

    def test_a_signature_exists_only_in_what_the_browser_sends_never_in_what_it_gets_back(self):
        carriers = sorted(name for name, schema in self.schemas.items()
                          if any("signature" in prop for prop in schema.get("properties", {})))
        self.assertEqual(carriers, ["PaymentVerifyRequest"])

    def test_the_payment_intent_has_exactly_the_fields_checkout_needs(self):
        self.assertEqual(
            set(self.schemas["PaymentIntentResponse"]["properties"]),
            {"order_id", "order_number", "razorpay_order_id", "razorpay_key_id", "amount_paise", "currency"},
        )

    def test_the_order_payment_summary_stays_tiny(self):
        self.assertEqual(set(self.schemas["OrderPaymentInfo"]["properties"]), {"last_attempt", "refund_pending"})

    def test_starting_a_payment_takes_no_body_so_the_client_cannot_name_an_amount(self):
        app = FastAPI()
        app.include_router(payments_api.router)
        operation = app.openapi()["paths"]["/api/orders/{order_id}/payment"]["post"]
        self.assertNotIn("requestBody", operation)
        self.assertEqual([p["name"] for p in operation.get("parameters", [])], ["order_id"])


if __name__ == "__main__":
    unittest.main()
