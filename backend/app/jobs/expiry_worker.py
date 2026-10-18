"""
The expiry job, running inside the web server.

No Redis, no Celery: one asyncio task started with the application, which
every `ORDER_EXPIRY_INTERVAL_SECONDS` runs a pass in a worker thread (so the
database work never blocks request handling) and goes back to sleep. A pass
that fails is logged and tried again next time; the loop itself never dies.

Several server processes can each run this at once: every order is locked with
SKIP LOCKED and expired by a compare-and-set, so they cannot expire or release
anything twice. Switch it off with ORDER_EXPIRY_WORKER_ENABLED=false (and run
`python -m app.jobs.expire_orders` from cron instead).

Use it as the application's lifespan - see `expiry_lifespan`.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.order_expiry_service import run_expiry_pass

logger = logging.getLogger(__name__)


async def expiry_loop(
    session_factory: Callable[[], Session],
    *,
    interval: float,
    batch_size: int,
    stop: Optional[asyncio.Event] = None,
) -> None:
    stop = stop or asyncio.Event()
    logger.info("Order expiry worker started (every %ss, batches of %d)", interval, batch_size)
    while not stop.is_set():
        try:
            await asyncio.to_thread(run_expiry_pass, session_factory, batch_size=batch_size)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the loop must survive a failed pass
            logger.exception("Order expiry pass failed; trying again in %ss", interval)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
    logger.info("Order expiry worker stopped")


@asynccontextmanager
async def expiry_lifespan(app=None) -> AsyncIterator[None]:
    """`FastAPI(..., lifespan=expiry_lifespan)`. Starts the loop on startup and
    stops it cleanly on shutdown. Does nothing if the worker is disabled."""
    if not settings.ORDER_EXPIRY_WORKER_ENABLED:
        logger.info("Order expiry worker is disabled (ORDER_EXPIRY_WORKER_ENABLED=false)")
        yield
        return
    from app.database.session import SessionLocal

    stop = asyncio.Event()
    task = asyncio.create_task(
        expiry_loop(
            SessionLocal,
            interval=settings.ORDER_EXPIRY_INTERVAL_SECONDS,
            batch_size=settings.ORDER_EXPIRY_BATCH_SIZE,
            stop=stop,
        ),
        name="order-expiry-worker",
    )
    try:
        yield
    finally:
        stop.set()
        try:
            await asyncio.wait_for(task, timeout=30)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()
