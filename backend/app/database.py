from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

settings.data_path.mkdir(parents=True, exist_ok=True)
(settings.data_path / "uploads").mkdir(exist_ok=True)
(settings.data_path / "backups").mkdir(exist_ok=True)

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False, "timeout": 30})


@event.listens_for(engine, "connect")
def sqlite_settings(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
