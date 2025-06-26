import asyncio
from contextvars import ContextVar
from logging.config import fileConfig
from typing import Any, Callable, Literal, TypedDict

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.sql.schema import SchemaItem

import app.database  # noqa: F401 # type: ignore
from alembic import context
from alembic.environment import EnvironmentContext
from app.base import Base
from app.config import Environment, settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None and settings.environment != Environment.TEST:
    fileConfig(config.config_file_name)


current_url = config.get_main_option("sqlalchemy.url", None)
if not current_url:
    config.set_main_option("sqlalchemy.url", settings.database_url)

ctx_var: ContextVar[dict[str, Any]] = ContextVar("ctx_var")

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(
    object: SchemaItem,
    name: str | None,
    type_: Literal[
        "schema",
        "table",
        "column",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
    ],
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    # 1) skip the built-in PostGIS table
    if type_ == "table" and name == "spatial_ref_sys":
        return False

    # 2) skip any Index that was declared/reflects with USING='gist'
    #    this covers op.create_index(..., postgresql_using='gist')
    #    and the corresponding drops in autogenerate.
    if type_ == "index":
        # Alembic passes you the Index object; dialect_options holds
        # any dialect-specific args (like postgresql_using)
        dialect_opts = getattr(object, "dialect_options", {})
        pg_opts = dialect_opts.get("postgresql", {})
        if pg_opts.get("using") == "gist":
            return False

    # otherwise include everything
    return True


class ConfigOptions(TypedDict):
    compare_type: bool
    compare_server_default: bool
    include_object: Callable[
        [
            SchemaItem,
            str | None,
            Literal[
                "schema",
                "table",
                "column",
                "index",
                "unique_constraint",
                "foreign_key_constraint",
            ],
            bool,
            SchemaItem | None,
        ],
        bool,
    ]


config_options: ConfigOptions = ConfigOptions(
    compare_type=True,
    compare_server_default=True,
    include_object=include_object,
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **config_options,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            **config_options,
        )

        with context.begin_transaction():
            context.run_migrations()
    except AttributeError:
        context_data = ctx_var.get()
        with EnvironmentContext(
            config=context_data["config"],
            script=context_data["script"],
            **context_data["opts"],
        ):
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                **config_options,
            )
            with context.begin_transaction():
                context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    try:
        _ = asyncio.get_running_loop()
    except RuntimeError:
        # there is no loop, can use asyncio.run
        asyncio.run(run_async_migrations())
        return

    from app.migration_state import set_migration_task

    ctx_var.set(
        {
            "config": context.config,
            "script": context.script,
            "opts": context._proxy.context_opts,  # type: ignore
        }
    )
    set_migration_task(asyncio.create_task(run_async_migrations()))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
