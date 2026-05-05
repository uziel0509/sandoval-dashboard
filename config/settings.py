"""
Sandoval SaaS — Configuración centralizada con Pydantic Settings
Reemplaza os.getenv() dispersos por atributos tipados.
"""
import os
from pathlib import Path

try:
    from pydantic_settings import BaseSettings
    _USE_PYDANTIC = True
except ImportError:
    _USE_PYDANTIC = False


if _USE_PYDANTIC:
    class Settings(BaseSettings):
        telegram_token: str = ""
        allowed_users: str = ""
        storage_secret: str = ""
        groq_api_key: str = ""
        database_url: str = ""
        cors_origins: str = (
            "http://187.77.62.67,"
            "http://187.77.62.67:8000,"
            "http://localhost:3000,"
            "http://localhost:8000"
        )
        base_dir: Path = Path("/var/www/sandoval")

        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"

    settings = Settings()

else:
    # Fallback si pydantic-settings no está instalado
    class _FallbackSettings:
        telegram_token   = os.getenv("TELEGRAM_TOKEN", "")
        allowed_users    = os.getenv("ALLOWED_USERS", "")
        storage_secret   = os.getenv("STORAGE_SECRET", "")
        groq_api_key     = os.getenv("GROQ_API_KEY", "")
        database_url     = os.getenv("DATABASE_URL", "")
        cors_origins     = os.getenv(
            "CORS_ORIGINS",
            "http://187.77.62.67,http://187.77.62.67:8000,http://localhost:3000"
        )
        base_dir         = Path(os.getenv("BASE_DIR", "/var/www/sandoval"))

    settings = _FallbackSettings()


# Shortcuts convenientes
BASE_DIR      = settings.base_dir
STATIC_DIR    = BASE_DIR / "static"
FACTURAS_DIR  = STATIC_DIR / "facturas"
EVIDENCIA_DIR = STATIC_DIR / "evidencia"
PDFS_DIR      = BASE_DIR / "pdfs"

# Lista de orígenes CORS como lista Python
CORS_ORIGINS_LIST = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
