from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    data_dir: str = "backend/data"
    session_secret: str = "development-only-change-me-please"
    initial_admin_email: str = "admin@gmail.com"
    initial_admin_password: str = "admin@123"
    initial_admin_name: str = "EMOTO Administrator"
    session_hours: int = 12
    allowed_origins: str = "http://localhost:5173,http://localhost:10000"
    public_base_url: str | None = None

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.production and (
            self.session_secret == "development-only-change-me-please"
            or len(self.session_secret) < 32
        ):
            raise ValueError("SESSION_SECRET must be a unique value of at least 32 characters in production")
        return self

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute() and not path.exists() and Path("../", self.data_dir).exists():
            path = Path("../", self.data_dir)
        return path.resolve()

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_path / 'emoto.db').as_posix()}"

    @property
    def production(self) -> bool:
        return self.app_env.lower() == "production"


settings = Settings()

