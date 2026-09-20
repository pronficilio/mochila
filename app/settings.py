from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: str
    redis_url: str = "redis://redis:6379/0"
    data_dir: Path = Path("/data")
    job_ttl_seconds: int = 86400
    file_ttl_seconds: int = 86400
    max_filesize: str = "2G"
    download_timeout_seconds: int = 3600
    default_max_height: int = 1080

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
