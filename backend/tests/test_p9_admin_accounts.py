"""
Phase 9 M1 - making and removing administrators (service + command line).

  AdminAccountServiceTests   promote / revoke rules, audit rows, case handling
  LastAdminTests             the last active admin cannot be removed (incl. a real race)
  CreateAdminScriptTests     python -m scripts.create_admin: output, exit codes, no secrets
"""

import io
import unittest

from sqlalchemy import func

from app.core.exceptions import AdminAccountError, AdminAccountNotFoundError, LastAdminError
from app.models import AdminAuditEvent, User, UserRole
from app.services.admin_account_service import AdminAccountService
from app.services.audit_service import CLI_ACTOR
from scripts import create_admin
from tests.p9_support import AdminTestCase
from tests.pg_support import new_session, run_concurrently


class AdminAccountServiceTests(AdminTestCase):
    def audit_rows(self):
        with new_session() as s:
            return s.query(AdminAuditEvent).order_by(AdminAuditEvent.created_at).all()

    def test_promote_makes_a_registered_customer_an_admin_and_audits_it(self):
        user = self.make_user()
        result = AdminAccountService(new_session()).promote(user.email)
        self.assertTrue(result.changed)
        self.assertEqual(self.role_in_db(user.id), UserRole.ADMIN)
        (row,) = self.audit_rows()
        self.assertEqual((row.action, row.entity_type, row.entity_id), ("user.promote_admin", "user", user.id))
        self.assertEqual((row.admin_user_id, row.admin_email), (None, CLI_ACTOR))
        self.assertEqual((row.before, row.after), ({"role": "customer"}, {"role": "admin"}))

    def test_promote_is_idempotent_and_writes_no_second_audit_row(self):
        user = self.make_user()
        AdminAccountService(new_session()).promote(user.email)
        again = AdminAccountService(new_session()).promote(user.email)
        self.assertFalse(again.changed)
        self.assertEqual(len(self.audit_rows()), 1)

    def test_email_matching_ignores_case_and_surrounding_spaces(self):
        user = self.make_user()
        AdminAccountService(new_session()).promote(f"  {user.email.upper()} ")
        self.assertEqual(self.role_in_db(user.id), UserRole.ADMIN)

    def test_an_unknown_email_is_refused_and_nothing_is_created(self):
        with self.assertRaises(AdminAccountNotFoundError):
            AdminAccountService(new_session()).promote("nobody@example.com")
        with new_session() as s:
            self.assertEqual(s.query(User).count(), 0)
            self.assertEqual(s.query(AdminAuditEvent).count(), 0)

    def test_a_blank_email_is_refused(self):
        for value in ["", "   ", None]:
            with self.subTest(value=value), self.assertRaises(AdminAccountError):
                AdminAccountService(new_session()).promote(value)

    def test_a_deactivated_account_cannot_be_promoted(self):
        user = self.make_user()
        self.set_role(user, active=False)
        with self.assertRaises(AdminAccountError):
            AdminAccountService(new_session()).promote(user.email)
        self.assertEqual(self.role_in_db(user.id), UserRole.CUSTOMER)

    def test_two_accounts_differing_only_by_case_are_never_guessed_between(self):
        a = self.make_user()
        b = self.make_user()
        with new_session() as s:
            s.get(User, a.id).email = "Same@Example.com"
            s.get(User, b.id).email = "same@example.com"
            s.commit()
        with self.assertRaises(AdminAccountError):
            AdminAccountService(new_session()).promote("SAME@example.com")
        self.assertEqual((self.role_in_db(a.id), self.role_in_db(b.id)), (UserRole.CUSTOMER, UserRole.CUSTOMER))

    def test_revoke_returns_an_admin_to_customer_and_audits_it(self):
        keeper, leaving = self.make_admin(), self.make_admin()
        result = AdminAccountService(new_session()).revoke(leaving.email)
        self.assertTrue(result.changed)
        self.assertEqual(self.role_in_db(leaving.id), UserRole.CUSTOMER)
        self.assertEqual(self.role_in_db(keeper.id), UserRole.ADMIN)
        (row,) = self.audit_rows()
        self.assertEqual((row.action, row.before, row.after), ("user.revoke_admin", {"role": "admin"}, {"role": "customer"}))

    def test_revoking_a_customer_changes_nothing(self):
        self.make_admin()
        user = self.make_user()
        self.assertFalse(AdminAccountService(new_session()).revoke(user.email).changed)
        self.assertEqual(self.audit_rows(), [])

    def test_list_admins_includes_deactivated_ones(self):
        a, b = self.make_admin(), self.make_admin(active=False)
        self.make_user()
        emails = {u.email for u in AdminAccountService(self.db).list_admins()}
        self.assertEqual(emails, {a.email, b.email})


class LastAdminTests(AdminTestCase):
    def test_the_only_admin_cannot_be_revoked(self):
        only = self.make_admin()
        with self.assertRaises(LastAdminError):
            AdminAccountService(new_session()).revoke(only.email)
        self.assertEqual(self.role_in_db(only.id), UserRole.ADMIN)
        with new_session() as s:
            self.assertEqual(s.query(AdminAuditEvent).count(), 0)

    def test_a_deactivated_admin_does_not_count_as_someone_else(self):
        only = self.make_admin()
        self.make_admin(active=False)
        with self.assertRaises(LastAdminError):
            AdminAccountService(new_session()).revoke(only.email)

    def test_a_deactivated_admin_can_always_be_revoked(self):
        self.make_admin()
        gone = self.make_admin(active=False)
        AdminAccountService(new_session()).revoke(gone.email)
        self.assertEqual(self.role_in_db(gone.id), UserRole.CUSTOMER)

    def test_the_admin_rows_are_really_locked_while_a_revocation_decides(self):
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError

        from app.repositories.admin_account_repository import AdminAccountRepository

        self.make_admin()
        self.make_admin()
        holder, waiter = new_session(), new_session()
        try:
            self.assertEqual(len(AdminAccountRepository(holder).lock_active_admins()), 2)
            waiter.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with self.assertRaises(OperationalError):
                AdminAccountRepository(waiter).lock_active_admins()
        finally:
            waiter.rollback()
            holder.rollback()
            waiter.close()
            holder.close()

    def test_two_simultaneous_revocations_leave_one_admin(self):
        a, b = self.make_admin(), self.make_admin()

        def revoke(email):
            def job():
                s = new_session()
                try:
                    return AdminAccountService(s).revoke(email).changed
                finally:
                    s.close()

            return job

        results = run_concurrently([revoke(a.email), revoke(b.email)])
        outcomes = sorted(kind for kind, _ in results)
        errors = [v for kind, v in results if kind == "err"]
        self.assertEqual(outcomes, ["err", "ok"], results)
        self.assertIsInstance(errors[0], LastAdminError)
        with new_session() as s:
            self.assertEqual(s.query(func.count(User.id)).filter(User.role == UserRole.ADMIN).scalar(), 1)


class CreateAdminScriptTests(AdminTestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = create_admin.main(list(argv), session_factory=new_session, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def test_promote(self):
        user = self.make_user()
        code, out, err = self.run_cli(user.email)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("is now an administrator", out)
        self.assertEqual(self.role_in_db(user.id), UserRole.ADMIN)

    def test_promote_again_is_a_success_that_says_nothing_changed(self):
        user = self.make_user()
        self.run_cli(user.email)
        code, out, _ = self.run_cli(user.email)
        self.assertEqual(code, 0)
        self.assertIn("already an administrator", out)

    def test_unknown_email_exits_1_with_a_clear_message(self):
        code, out, err = self.run_cli("nobody@example.com")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Register it first", err)

    def test_revoke_and_the_last_admin_guard(self):
        only = self.make_admin()
        code, _, err = self.run_cli("--revoke", only.email)
        self.assertEqual(code, 1)
        self.assertIn("last active administrator", err)
        second = self.make_user()
        self.run_cli(second.email)
        code, out, _ = self.run_cli("--revoke", only.email)
        self.assertEqual(code, 0)
        self.assertIn("no longer an administrator", out)

    def test_list(self):
        code, out, _ = self.run_cli("--list")
        self.assertEqual((code, out.strip()), (0, "No administrators yet."))
        admin = self.make_admin()
        _, out, _ = self.run_cli("--list")
        self.assertIn(admin.email, out)
        self.assertIn("active", out)

    def test_usage_errors_exit_2(self):
        for argv in [(), ("--list", "x@example.com"), ("--list", "--revoke")]:
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err)

    def test_output_never_contains_a_password_hash(self):
        user = self.make_user()
        with new_session() as s:
            s.get(User, user.id).password_hash = "$2b$12$THISISASECRETHASHVALUEthatmustneverbeprinted"
            s.commit()
        for argv in [(user.email,), ("--list",), ("--revoke", user.email)]:
            _, out, err = self.run_cli(*argv)
            self.assertNotIn("THISISASECRET", out + err)

    def test_the_script_reads_no_password_and_has_no_embedded_credentials(self):
        import inspect
        import re

        source = inspect.getsource(create_admin)
        self.assertNotIn("getpass", source)
        self.assertNotIn("input(", source)
        self.assertIsNone(re.search(r"@[a-z0-9-]+\.[a-z]{2,}", source.replace("you@example.com", "")), "an email address is embedded in the script")


if __name__ == "__main__":
    unittest.main()
