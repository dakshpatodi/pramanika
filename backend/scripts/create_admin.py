"""
Create (promote) or remove an administrator.

Run from backend/, with the venv active and DATABASE_URL pointing at the
database you mean:

    python -m scripts.create_admin you@example.com           promote
    python -m scripts.create_admin --revoke you@example.com  back to customer
    python -m scripts.create_admin --list                    show administrators

How the first administrator is made:
  1. Register normally (the site, or POST /api/auth/register).
  2. Run the command above with that email.
There is no password prompt, no default account and no public endpoint:
whoever can run this on the server decides who administers the shop. The
change takes effect on that user's very next request (the role is read from
the database each time) and is written to the admin audit trail.

Exit status: 0 success (including "already an administrator"), 1 refused or
failed, 2 bad usage.
"""

import argparse
import sys
from typing import Callable, List, Optional, TextIO

from sqlalchemy.orm import Session

from app.core.exceptions import DomainError
from app.services.admin_account_service import AdminAccountService


def _session_factory() -> Session:
    from app.database.session import SessionLocal

    return SessionLocal()


def main(
    argv: Optional[List[str]] = None,
    *,
    session_factory: Callable[[], Session] = _session_factory,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
) -> int:
    parser = argparse.ArgumentParser(prog="create_admin", description="Promote or demote a registered account.")
    parser.add_argument("email", nargs="?", help="email of an already registered account")
    parser.add_argument("--revoke", action="store_true", help="return the account to a customer")
    parser.add_argument("--list", action="store_true", dest="list_admins", help="list administrators and exit")

    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_:
        return int(exit_.code or 0)

    if args.list_admins:
        if args.email or args.revoke:
            print("--list takes no email and cannot be combined with --revoke.", file=err)
            return 2
    elif not args.email:
        print("An email address is required (or use --list).", file=err)
        return 2

    db = session_factory()
    try:
        service = AdminAccountService(db)
        if args.list_admins:
            admins = service.list_admins()
            if not admins:
                print("No administrators yet.", file=out)
            for admin in admins:
                state = "active" if admin.is_active else "DEACTIVATED"
                print(f"{admin.email}  ({state})", file=out)
            return 0

        if args.revoke:
            result = service.revoke(args.email)
            verb = "is no longer an administrator" if result.changed else "was not an administrator (nothing changed)"
        else:
            result = service.promote(args.email)
            verb = "is now an administrator" if result.changed else "was already an administrator (nothing changed)"
        print(f"{result.user.email} {verb}.", file=out)
        return 0
    except DomainError as exc:
        print(f"Refused: {exc.message}", file=err)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
