"""
Shared harness for the PostgreSQL integration tests (Phase 6).

These tests exercise row locks, conditional UPDATEs and unique indexes,
which SQLite cannot imitate - so they run against a REAL PostgreSQL
database and are skipped when none is configured.

Setup (once), against a THROWAWAY database - never your development one:

    docker exec -it healthy-harvest-postgres createdb -U healthy_harvest pramanika_test
    $env:DATABASE_URL = "postgresql+psycopg2://healthy_harvest:<password>@localhost:5432/pramanika_test"
    alembic upgrade head
    $env:TEST_DATABASE_URL = $env:DATABASE_URL

(PowerShell; use `export` in bash.) Then run the tests, e.g.

    python -m unittest tests.test_p6_reservations -v

Safety: the harness EMPTIES every table before each test, so it refuses to
run unless the database name contains "test".
"""

import os
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import make_url

from app.models import (
    Address,
    Category,
    Coupon,
    DiscountType,
    Inventory,
    Order,
    OrderInventoryState,
    OrderItem,
    OrderPaymentStatus,
    OrderStatus,
    Product,
    User,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

_engine = None
_SessionFactory = None
_counter = 0


def _get_engine():
    global _engine, _SessionFactory
    if _engine is None:
        db_name = make_url(TEST_DATABASE_URL).database or ""
        if "test" not in db_name.lower():
            raise RuntimeError(
                f"Refusing to run: TEST_DATABASE_URL points at '{db_name}'. The integration tests empty every "
                "table, so the database name must contain 'test'."
            )
        engine = create_engine(TEST_DATABASE_URL, pool_size=20, max_overflow=20, pool_pre_ping=True, future=True)
        columns = {c["name"] for c in inspect(engine).get_columns("orders")}
        if "inventory_state" not in columns:
            raise RuntimeError(
                "The test database has not been migrated to the Phase 6 schema. "
                "Run `alembic upgrade head` against it first."
            )
        _engine = engine
        _SessionFactory = sessionmaker(bind=engine, autoflush=False, future=True)
    return _engine


def new_session() -> Session:
    _get_engine()
    return _SessionFactory()


def _unique() -> int:
    global _counter
    _counter += 1
    return _counter


class PostgresTestCase(unittest.TestCase):
    """Skips without TEST_DATABASE_URL; otherwise gives every test an empty
    database and a session (`self.db`)."""

    @classmethod
    def setUpClass(cls):
        if not TEST_DATABASE_URL:
            raise unittest.SkipTest("TEST_DATABASE_URL is not set - skipping PostgreSQL integration tests.")
        _get_engine()

    def setUp(self):
        engine = _get_engine()
        with engine.begin() as conn:
            tables = [
                row[0]
                for row in conn.execute(
                    text("select tablename from pg_tables where schemaname = 'public' and tablename <> 'alembic_version'")
                )
            ]
            if tables:
                conn.execute(text("TRUNCATE TABLE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))
        self.db = new_session()
        self.addCleanup(self.db.close)

    # --- builders (each commits, so other sessions/threads can see the rows) ---

    def make_user(self) -> User:
        n = _unique()
        user = User(
            first_name="Test",
            last_name=f"User{n}",
            email=f"user{n}@example.com",
            phone_number=f"9{n:09d}",
            password_hash="x",
        )
        self.db.add(user)
        self.db.commit()
        return user

    def make_product(
        self,
        *,
        price: str = "100.00",
        stock: int = 10,
        reserved: int = 0,
        active: bool = True,
        name: Optional[str] = None,
    ) -> Product:
        n = _unique()
        category = self.db.query(Category).first()
        if category is None:
            category = Category(name="Cereals", slug="cereals")
            self.db.add(category)
            self.db.flush()
        product = Product(
            category_id=category.id,
            name=name or f"Product {n}",
            slug=f"product-{n}",
            sku=f"SKU-{n}",
            price=Decimal(price),
            is_active=active,
        )
        self.db.add(product)
        self.db.flush()
        self.db.add(Inventory(product_id=product.id, quantity=stock, reserved_quantity=reserved))
        self.db.commit()
        return product

    def make_coupon(self, **overrides) -> Coupon:
        n = _unique()
        values = dict(
            code=f"CODE{n}",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10"),
            usage_limit=None,
            used_count=0,
            is_active=True,
        )
        values.update(overrides)
        coupon = Coupon(**values)
        self.db.add(coupon)
        self.db.commit()
        return coupon

    def make_address(self, user: User) -> Address:
        address = Address(
            user_id=user.id,
            full_name="Test User",
            phone_number="9000000000",
            address_line_1="1 Test Street",
            city="Pune",
            state="Maharashtra",
            postal_code="411001",
        )
        self.db.add(address)
        self.db.commit()
        return address

    def make_order(
        self,
        user: User,
        lines: Iterable[Tuple[Product, int]],
        *,
        inventory_state: OrderInventoryState = OrderInventoryState.RESERVED,
        status: OrderStatus = OrderStatus.PENDING,
        payment_status: OrderPaymentStatus = OrderPaymentStatus.PENDING,
        coupon: Optional[Coupon] = None,
        reserve_stock: bool = True,
    ) -> Order:
        """An order as checkout would leave it. With `reserve_stock` the
        inventory rows are bumped too, so the books balance."""
        lines = list(lines)
        subtotal = sum(Decimal(str(p.price)) * q for p, q in lines)
        order = Order(
            user_id=user.id,
            order_number=f"T-{_unique()}",
            subtotal=subtotal,
            total_amount=subtotal,
            status=status,
            payment_status=payment_status,
            inventory_state=inventory_state,
            coupon_id=coupon.id if coupon else None,
            coupon_code=coupon.code if coupon else None,
        )
        for product, quantity in lines:
            order.items.append(
                OrderItem(
                    product_id=product.id,
                    product_name_snapshot=product.name,
                    sku_snapshot=product.sku,
                    unit_price=product.price,
                    quantity=quantity,
                    subtotal=Decimal(str(product.price)) * quantity,
                )
            )
            if reserve_stock and inventory_state == OrderInventoryState.RESERVED:
                self.db.query(Inventory).filter(Inventory.product_id == product.id).update(
                    {Inventory.reserved_quantity: Inventory.reserved_quantity + quantity}
                )
        self.db.add(order)
        self.db.commit()
        return order

    # --- readers (always fresh) ---

    def stock(self, product: Product) -> Tuple[int, int]:
        """(quantity, reserved_quantity) as committed in the database."""
        with new_session() as s:
            row = s.query(Inventory).filter(Inventory.product_id == product.id).one()
            return row.quantity, row.reserved_quantity

    def used_count(self, coupon: Coupon) -> int:
        with new_session() as s:
            return s.query(Coupon).filter(Coupon.id == coupon.id).one().used_count


def run_concurrently(jobs, timeout: float = 60.0):
    """Run each zero-argument callable in its own thread, released together
    by a barrier to maximise contention. Returns a list of
    ("ok", value) / ("err", exception) in job order, and fails if a job
    is still running after `timeout` seconds (a hang means a deadlock).
    Each job must open its own session via `new_session()`."""
    import threading

    barrier = threading.Barrier(len(jobs))
    results: List = [None] * len(jobs)

    def runner(index, job):
        try:
            barrier.wait(timeout=timeout)
            results[index] = ("ok", job())
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            results[index] = ("err", exc)

    threads = [threading.Thread(target=runner, args=(i, job), daemon=True) for i, job in enumerate(jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout)
    hung = [i for i, t in enumerate(threads) if t.is_alive()]
    if hung:
        raise AssertionError(f"{len(hung)} concurrent job(s) did not finish within {timeout}s - likely a deadlock")
    return results