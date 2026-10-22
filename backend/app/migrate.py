"""Safe database initialization shared by local and serverless startup."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from . import models  # noqa: F401 - registers every table on Base.metadata
from .database import Base, engine


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return config


def migrate_database() -> None:
    """Initialize an empty database or upgrade an existing one in place.

    The historical first migration calls ``Base.metadata.create_all``. On a new
    checkout that metadata already contains columns introduced by later
    migrations, so replaying every migration would try to add them twice. Only
    a genuinely empty database is initialized from current metadata and stamped
    at head. Any database containing tables follows the normal Alembic upgrade
    path and is never recreated.
    """

    config = alembic_config()
    if not inspect(engine).get_table_names():
        Base.metadata.create_all(engine)
        command.stamp(config, "head")
        return
    command.upgrade(config, "head")


if __name__ == "__main__":
    migrate_database()
