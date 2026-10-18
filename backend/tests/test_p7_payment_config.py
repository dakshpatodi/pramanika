"""Phase 7 / Milestone 1: Razorpay configuration (pure - no database, no network)."""

import importlib
import inspect
import logging
import os
import pkgutil
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.exceptions import DomainError, PaymentsNotConfiguredError
from app.core.payment_config import (
    RazorpayCredentials,
    get_razorpay_credentials,
    get_razorpay_webhook_secret,
    public_key_id,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Obviously fake values - shaped like real ones so the format checks run.
KEY_ID = "rzp_test_FAKEKEYID000000"
KEY_SECRET = "fake-key-secret-DO-NOT-LEAK-111"
WEBHOOK_SECRET = "fake-webhook-secret-DO-NOT-LEAK-222"


def make_settings(**overrides) -> Settings:
    """A Settings built from explicit values only: no .env file, and no
    RAZORPAY_* variables inherited from the developer's environment."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("RAZORPAY_") and k != "ORDER_PAYMENT_WINDOW_MINUTES"}
    with patch.dict(os.environ, env, clear=True):
        return Settings(_env_file=None, **overrides)


def configured(**overrides) -> Settings:
    values = dict(RAZORPAY_KEY_ID=KEY_ID, RAZORPAY_KEY_SECRET=KEY_SECRET, RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET)
    values.update(overrides)
    return make_settings(**values)


class MissingCredentialsTests(unittest.TestCase):
    def test_defaults_are_empty_and_app_still_starts(self):
        s = make_settings()
        self.assertEqual(s.RAZORPAY_KEY_ID, "")
        self.assertEqual(s.RAZORPAY_KEY_SECRET.get_secret_value(), "")
        self.assertEqual(s.RAZORPAY_WEBHOOK_SECRET.get_secret_value(), "")
        self.assertFalse(s.RAZORPAY_TEST_MODE)

    def test_credentials_are_refused_when_nothing_is_set(self):
        with self.assertRaises(PaymentsNotConfiguredError):
            get_razorpay_credentials(make_settings())

    def test_each_missing_piece_is_refused(self):
        for overrides in (
            dict(RAZORPAY_KEY_SECRET=KEY_SECRET),                      # no key id
            dict(RAZORPAY_KEY_ID=KEY_ID),                              # no secret
            dict(RAZORPAY_KEY_ID=KEY_ID, RAZORPAY_KEY_SECRET="   "),   # blank secret
        ):
            with self.subTest(overrides=sorted(overrides)):
                with self.assertRaises(PaymentsNotConfiguredError):
                    get_razorpay_credentials(make_settings(**overrides))

    def test_webhook_secret_is_refused_when_unset_even_if_keys_are_set(self):
        s = configured(RAZORPAY_WEBHOOK_SECRET="")
        get_razorpay_credentials(s)  # keys fine
        with self.assertRaises(PaymentsNotConfiguredError):
            get_razorpay_webhook_secret(s)

    def test_error_is_a_503_with_a_generic_message_that_names_no_setting(self):
        err = PaymentsNotConfiguredError()
        self.assertIsInstance(err, DomainError)
        self.assertEqual(err.http_status, 503)
        self.assertNotIn("RAZORPAY", err.message.upper())
        self.assertNotIn("secret", err.message.lower())
        self.assertNotIn("key", err.message.lower())

    def test_the_log_names_the_missing_setting_but_never_a_value(self):
        s = make_settings(RAZORPAY_KEY_ID=KEY_ID)  # secret missing
        with self.assertLogs("app.core.payment_config", level=logging.ERROR) as logs:
            with self.assertRaises(PaymentsNotConfiguredError):
                get_razorpay_credentials(s)
        text = "\n".join(logs.output)
        self.assertIn("RAZORPAY_KEY_SECRET", text)
        self.assertNotIn(KEY_ID, text)


class ValidConfigurationTests(unittest.TestCase):
    def test_valid_configuration_yields_credentials(self):
        s = configured()
        creds = get_razorpay_credentials(s)
        self.assertEqual(creds.key_id, KEY_ID)
        self.assertEqual(creds.key_secret, KEY_SECRET)
        self.assertEqual(get_razorpay_webhook_secret(s), WEBHOOK_SECRET)
        self.assertTrue(s.RAZORPAY_TEST_MODE)

    def test_public_key_id_is_the_key_id(self):
        self.assertEqual(public_key_id(configured()), KEY_ID)

    def test_whitespace_around_values_is_trimmed(self):
        s = configured(RAZORPAY_KEY_ID=f"  {KEY_ID}  ", RAZORPAY_KEY_SECRET=f" {KEY_SECRET}\n")
        creds = get_razorpay_credentials(s)
        self.assertEqual((creds.key_id, creds.key_secret), (KEY_ID, KEY_SECRET))

    def test_values_are_read_from_the_environment(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("RAZORPAY_")}
        env.update(RAZORPAY_KEY_ID=KEY_ID, RAZORPAY_KEY_SECRET=KEY_SECRET, RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET)
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=None)
        self.assertEqual(get_razorpay_credentials(s).key_secret, KEY_SECRET)

    def test_payment_window_defaults_to_30_minutes_and_is_bounded(self):
        self.assertEqual(make_settings().ORDER_PAYMENT_WINDOW_MINUTES, 30)
        self.assertEqual(make_settings(ORDER_PAYMENT_WINDOW_MINUTES=45).ORDER_PAYMENT_WINDOW_MINUTES, 45)
        for bad in (0, -5, 100000):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                make_settings(ORDER_PAYMENT_WINDOW_MINUTES=bad)

    def test_timeout_is_positive_and_capped(self):
        self.assertGreater(make_settings().RAZORPAY_TIMEOUT_SECONDS, 0)
        for bad in (0, -1, 600):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                make_settings(RAZORPAY_TIMEOUT_SECONDS=bad)


class KeyFormatAndModeTests(unittest.TestCase):
    def test_malformed_key_ids_are_rejected(self):
        for bad in ("not-a-key", "rzp_", "rzp_test_", "rzp_prod_abc123", "RZP_TEST_abc123"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                make_settings(RAZORPAY_KEY_ID=bad)

    def test_a_live_key_is_refused_outside_production(self):
        for env_name in ("development", "test", "staging"):
            with self.subTest(env=env_name), self.assertRaises(ValidationError) as ctx:
                make_settings(RAZORPAY_KEY_ID="rzp_live_FAKEKEYID000000", APP_ENV=env_name)
            self.assertIn("LIVE", str(ctx.exception))

    def test_a_live_key_is_allowed_in_production(self):
        s = make_settings(
            RAZORPAY_KEY_ID="rzp_live_FAKEKEYID000000",
            RAZORPAY_KEY_SECRET=KEY_SECRET,
            APP_ENV="production",
            SECRET_KEY="a-real-production-secret",
        )
        self.assertFalse(s.RAZORPAY_TEST_MODE)

    def test_test_keys_report_test_mode(self):
        self.assertTrue(configured().RAZORPAY_TEST_MODE)


class SecretsAreNotExposedTests(unittest.TestCase):
    def setUp(self):
        self.settings = configured()

    def assert_no_secret_in(self, text: str):
        self.assertNotIn(KEY_SECRET, text)
        self.assertNotIn(WEBHOOK_SECRET, text)

    def test_settings_repr_str_and_json_hide_both_secrets(self):
        self.assert_no_secret_in(repr(self.settings))
        self.assert_no_secret_in(str(self.settings))
        self.assert_no_secret_in(self.settings.model_dump_json())
        self.assert_no_secret_in(str(self.settings.model_dump()))

    def test_credentials_repr_hides_the_secret(self):
        creds = get_razorpay_credentials(self.settings)
        self.assert_no_secret_in(repr(creds))
        self.assert_no_secret_in(str(creds))
        self.assertIn(KEY_ID, repr(creds))  # the public id may appear

    def test_credentials_are_immutable(self):
        creds = get_razorpay_credentials(self.settings)
        with self.assertRaises(Exception):
            creds.key_secret = "x"  # type: ignore[misc]

    def test_no_api_schema_has_a_secret_field(self):
        """Guard for the future: no response/request model may ever declare a
        field that could carry a secret to the browser."""
        import app.schemas as schemas_pkg

        offenders = []
        for mod in pkgutil.iter_modules(schemas_pkg.__path__):
            module = importlib.import_module(f"app.schemas.{mod.name}")
            for name, cls in inspect.getmembers(module, inspect.isclass):
                if issubclass(cls, BaseModel) and cls.__module__ == module.__name__:
                    for field_name in cls.model_fields:
                        if re.search(r"secret|signing|key_secret|webhook", field_name, re.I):
                            offenders.append(f"{cls.__name__}.{field_name}")
        self.assertEqual(offenders, [])


class RepositoryHygieneTests(unittest.TestCase):
    def test_env_example_holds_placeholders_only(self):
        text = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
        values = dict(
            line.split("=", 1) for line in text.splitlines() if "=" in line and not line.lstrip().startswith("#")
        )
        for name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"):
            self.assertIn(name, values, f"{name} missing from .env.example")
            self.assertEqual(values[name].strip(), "", f"{name} in .env.example must be empty")
        self.assertIsNone(re.search(r"rzp_(test|live)_[A-Za-z0-9]{6,}", text), "a real-looking key is in .env.example")
        self.assertEqual(values["ORDER_PAYMENT_WINDOW_MINUTES"].strip(), "30")

    def test_env_files_are_git_ignored_but_the_example_is_not(self):
        lines = {l.strip() for l in (BACKEND_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()}
        self.assertIn(".env", lines)
        self.assertIn("!.env.example", lines)

    def test_no_razorpay_credentials_are_hardcoded_in_source(self):
        # Anything key-shaped, except obvious placeholders such as rzp_test_xxxxxxxx.
        pattern = re.compile(r"rzp_(test|live)_(?!x+\b)[A-Za-z0-9]{8,}")
        offenders = []
        for path in (BACKEND_DIR / "app").rglob("*.py"):
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(BACKEND_DIR)))
        self.assertEqual(offenders, [])

    def test_the_hardcoded_key_pattern_catches_real_shaped_keys_but_not_placeholders(self):
        pattern = re.compile(r"rzp_(test|live)_(?!x+\b)[A-Za-z0-9]{8,}")
        self.assertTrue(pattern.search('KEY = "rzp_test_AbCdEf123456"'))
        self.assertTrue(pattern.search("rzp_live_9f8e7d6c5b4a3"))
        self.assertFalse(pattern.search("e.g. rzp_test_xxxxxxxxxxxxxx"))

    def test_httpx_is_a_pinned_runtime_dependency(self):
        reqs = (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(reqs, r"(?m)^httpx==\d+\.\d+\.\d+\s*$")


if __name__ == "__main__":
    unittest.main()
