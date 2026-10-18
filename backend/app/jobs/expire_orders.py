"""
Expire unpaid orders from the command line - for cron, Windows Task Scheduler,
or a one-off clean-up. The web server runs the same job in the background by
itself (see `app.jobs.expiry_worker`); use this if you run the API without it.

    python -m app.jobs.expire_orders                one pass, then exit
    python -m app.jobs.expire_orders --loop         keep running (Ctrl+C to stop)
    python -m app.jobs.expire_orders --batch-size 20 --interval 30 --loop

Exit status: 0 on success, 1 if any order failed to expire (it is retried on the
next pass).
"""

import argparse
import logging
import sys
import time
from typing import List, Optional

from app.core.config import settings
from app.database.session import SessionLocal
from app.services.order_expiry_service import run_expiry_pass

logger = logging.getLogger("app.jobs.expire_orders")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs.expire_orders", description=__doc__.split("\n\n")[0])
    parser.add_argument("--loop", action="store_true", help="keep running instead of one pass")
    parser.add_argument("--batch-size", type=int, default=settings.ORDER_EXPIRY_BATCH_SIZE)
    parser.add_argument("--interval", type=float, default=settings.ORDER_EXPIRY_INTERVAL_SECONDS,
                        help="seconds between passes with --loop")
    args = parser.parse_args(argv)
    if args.batch_size < 1 or args.interval <= 0:
        parser.error("--batch-size must be >= 1 and --interval > 0")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    failed = False
    try:
        while True:
            run = run_expiry_pass(SessionLocal, batch_size=args.batch_size)
            print(f"expired={run.expired} busy={run.busy} not_due={run.not_due} failed={run.failed}", flush=True)
            failed = failed or run.failed > 0
            if not args.loop:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("stopped", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
