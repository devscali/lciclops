"""
Configuración del backend - Little Caesars Reports
Aurelia: "Las variables de entorno van aquí, NUNCA hardcodeadas"
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Little Caesars Reports API"
    app_version: str = "1.0.0"
    debug: bool = False

    # Firebase
    firebase_project_id: str
    firebase_credentials_path: str = "firebase-credentials.json"

    # Claude API
    anthropic_api_key: str

    # CORS
    frontend_url: str = "http://localhost:3000"

    # Storage
    gcs_bucket: str = "little-caesars-documents"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
