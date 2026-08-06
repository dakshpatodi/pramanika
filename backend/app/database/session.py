"""
SQLAlchemy database setup.

Phase 1 note: this wires up the engine/session machinery only. No models
are defined and no tables are created yet - that begins in Phase 2 once
the product/category schema is designed.
"""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# The engine manages the actual connection pool to PostgreSQL.
# `pool_pre_ping` avoids "server has gone away" errors on idle connections.
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

# Each request gets its own Session from this factory.
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)


class Base(DeclarativeBase):
    """Shared declarative base that every future ORM model will inherit from."""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and always closes it.

    Usage (from Phase 2 onwards):

        @router.get("/products")
        def list_products(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
