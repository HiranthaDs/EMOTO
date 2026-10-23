"""Safe database initialization shared by local and serverless startup."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select

from . import models  # noqa: F401 - registers every table on Base.metadata
from .config import settings
from .database import Base, SessionLocal, engine
from .security import hash_password


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return config


def ensure_initial_admin() -> bool:
    """Create the configured Super Admin only when the users table is empty."""
    with SessionLocal.begin() as db:
        if db.scalar(select(func.count(models.User.id))):
            return False
        admin = models.User(
            email=settings.initial_admin_email.lower(),
            full_name=settings.initial_admin_name,
            password_hash=hash_password(settings.initial_admin_password),
            role="Super Admin",
        )
        db.add(admin)
        db.flush()
        db.add(models.AuditLog(
            user_id=admin.id,
            action="system.initial_admin",
            entity_type="user",
            entity_id=admin.id,
            details="Initial Super Admin created during database initialization",
        ))
        return True


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
    else:
        command.upgrade(config, "head")
    ensure_initial_admin()


if __name__ == "__main__":
    migrate_database()
