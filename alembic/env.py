from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── 모델 import (마이그레이션 자동 감지용) ─────────────────
from app.auth.models import *  # noqa: F401, F403
from app.chat.models import *  # noqa: F401, F403
from app.core.config import settings
from app.core.database import Base
from app.game.models import *  # noqa: F401, F403
from app.recommend.models import *  # noqa: F401, F403
from app.stat.models import *  # noqa: F401, F403
from app.steam.models import *  # noqa: F401, F403
from app.survey.models import *  # noqa: F401, F403

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# sync URL 주입 (DATABASE_SYNC_URL: psycopg2 드라이버)
config.set_main_option("sqlalchemy.url", settings.DATABASE_SYNC_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
