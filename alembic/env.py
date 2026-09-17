from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from models.account_magic_link_token_model import AccountMagicLinkToken
from models.account_flow_event_model import AccountFlowEvent
from models.account_identity_model import AccountIdentity
from models.account_model import Account
from models.account_session_model import AccountSession
from models.api_idempotency_key_model import ApiIdempotencyKey
from models.base import Base
from models.user_model import User
from models.design_model import Design
from models.design_draft_model import DesignDraft
from models.billing_event_model import BillingEvent
from models.billing_webhook_event_model import BillingWebhookEvent
from models.checkout_session_model import CheckoutSession
from models.furniture_search_draft_model import FurnitureSearchDraft
from models.job_model import Job
from models.promocode_model import Promocode
from models.payment_model import Payment
from models.promocode_usage_model import PromocodeUsage
from models.upload_intent_model import UploadIntent
from models.uploaded_file_model import UploadedFile

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    sqlalchemy_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://ar_admin:changeme@localhost:5432/ar_interior",
    )
    config.set_main_option("sqlalchemy.url", sqlalchemy_url)
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
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    sqlalchemy_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://ar_admin:changeme@localhost:5432/ar_interior",
    )
    config.set_main_option("sqlalchemy.url", sqlalchemy_url)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        class _Runner:
            def __init__(self, env_context):
                self._env_context = env_context

            def begin(self):
                return self._env_context.begin_transaction()

            def run_migrations(self):
                return self._env_context.run_migrations()

        runner = _Runner(context)
        with runner.begin():
            runner.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
