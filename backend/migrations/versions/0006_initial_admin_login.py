"""Apply the requested initial Super Admin login to an existing installation."""

from datetime import datetime, timezone

from alembic import op
from pwdlib import PasswordHash
import sqlalchemy as sa

from app.config import settings


revision = "0006_initial_admin_login"
down_revision = "0005_warranty_durations"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("email", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("role", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    audit_logs = sa.table(
        "audit_logs",
        sa.column("user_id", sa.Integer),
        sa.column("action", sa.String),
        sa.column("entity_type", sa.String),
        sa.column("entity_id", sa.Integer),
        sa.column("details", sa.Text),
        sa.column("ip_address", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    requested_email = settings.initial_admin_email.lower()
    target_id = bind.execute(
        sa.select(users.c.id).where(sa.func.lower(users.c.email) == requested_email)
    ).scalar_one_or_none()
    if target_id is None:
        target_id = bind.execute(
            sa.select(users.c.id)
            .where(users.c.role == "Super Admin")
            .order_by(users.c.id)
            .limit(1)
        ).scalar_one_or_none()
    if target_id is None:
        return

    password_hash = PasswordHash.recommended().hash(settings.initial_admin_password)
    bind.execute(
        users.update()
        .where(users.c.id == target_id)
        .values(
            email=requested_email,
            password_hash=password_hash,
            role="Super Admin",
            is_active=True,
        )
    )
    bind.execute(audit_logs.insert().values(
        user_id=target_id,
        action="system.initial_admin_credentials",
        entity_type="user",
        entity_id=target_id,
        details="Initial Super Admin login updated by migration",
        ip_address=None,
        created_at=datetime.now(timezone.utc),
    ))


def downgrade():
    # Credential changes are deliberately irreversible: restoring a previous
    # password hash would re-enable credentials that an operator may have retired.
    pass
