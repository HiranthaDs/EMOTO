"""Vercel entrypoint for the single-service EMOTO application.

Vercel Functions only allow writes below /tmp.  Each function instance therefore
gets its own temporary SQLite database, which is migrated before FastAPI starts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = PROJECT_ROOT / "backend"

# The Alembic environment and the application both import the backend package as
# ``app`` when they run outside Vercel, so expose the same import path here.
sys.path.insert(0, str(BACKEND_ROOT))


if os.environ.get("VERCEL"):
    os.environ.setdefault("APP_ENV", "production")
    os.environ.setdefault("DATA_DIR", "/tmp/emoto")
    from app.migrate import migrate_database

    migrate_database()

from app.main import app  # noqa: E402,F401
