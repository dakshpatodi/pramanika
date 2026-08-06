"""
Alembic environment script.

Wires Alembic's migration runner to this project's SQLAlchemy `Base` and
its `.env`-driven `Settings`, instead of hardcoding a DB URL in alembic.ini.

As of Phase 2, `app.models` is imported below, which registers the `User`
model against `Base.metadata`. Any new model added under `app/models/`
must be imported from `app/models/__init__.py` (not just written) or
Alembic will not see it during autogenerate.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.database.session import Base

# Alembic Config object, provides access to values in alembic.ini
config = context.config

# Inject the runtime database URL (from .env via Settings) into Alembic's config
config.set_main_option("sqlalchemy.url", settings.SQLALCHEMY_DATABASE_URL)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importing app.models (not just app.database.session) is what actually
# registers every model class against Base.metadata - without this line,
# Base.metadata would be empty and autogenerate would think every table
# should be dropped.
import app.models  # noqa: F401,E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without a live DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (applies changes via a live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()