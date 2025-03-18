"""Application settings loaded from environment variables (via pydantic-settings)."""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"
    LOG_LEVEL: str = "INFO"

    # PostgreSQL
    DATABASE_URL: str = "postgresql://routemonitor:password@localhost:5432/routemonitor"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # InfluxDB
    INFLUXDB_URL: str = "http://localhost:8086"
    INFLUXDB_TOKEN: str = "my-super-secret-auth-token"
    INFLUXDB_ORG: str = "myorg"
    INFLUXDB_BUCKET: str = "bgp_metrics"

    # BMP Server
    BMP_LISTEN_HOST: str = "0.0.0.0"
    BMP_LISTEN_PORT: int = 9179

    # Anomaly Detection
    ANOMALY_BASELINE_DAYS: int = 7
    ANOMALY_Z_SCORE_THRESHOLD: float = 3.0
    ANOMALY_DEDUP_WINDOW_SECONDS: int = 300  # 5 minutes

    # Alert channels
    SLACK_WEBHOOK_URL: str = ""
    PAGERDUTY_ROUTING_KEY: str = ""

    @model_validator(mode="after")
    def validate_secret_key_in_production(self):
        if self.APP_ENV == "production" and len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return self


settings = Settings()
