from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_password: str
    redis_url: str = "redis://redis:6379/0"
    data_dir: Path = Path("/data")
    job_ttl_seconds: int = 86400
    file_ttl_seconds: int = 86400
    max_filesize: str = "2G"
    download_timeout_seconds: int = 3600
    download_egress: Literal["direct", "residential"] = "direct"
    residential_proxy: SecretStr | None = None
    default_max_height: int = Field(default=1080, ge=144, le=1080)
    session_ttl_seconds: int = 30 * 24 * 60 * 60
    session_cookie_name: str = "mochila_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    login_max_attempts: int = 8
    login_window_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    @field_validator("residential_proxy", mode="before")
    @classmethod
    def empty_residential_proxy_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("residential_proxy")
    @classmethod
    def residential_proxy_must_be_socks(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value

        from urllib.parse import urlsplit

        proxy = urlsplit(value.get_secret_value())
        if proxy.scheme != "socks5":
            raise ValueError("RESIDENTIAL_PROXY must use socks5://")
        if not proxy.hostname:
            raise ValueError("RESIDENTIAL_PROXY must include a host")
        try:
            if proxy.port is None:
                raise ValueError("RESIDENTIAL_PROXY must include a port")
        except ValueError as exc:
            raise ValueError("RESIDENTIAL_PROXY must include a valid port") from exc
        if proxy.path or proxy.query or proxy.fragment:
            raise ValueError("RESIDENTIAL_PROXY must not include a path, query, or fragment")
        return value

    @model_validator(mode="after")
    def residential_egress_requires_proxy(self) -> "Settings":
        if self.download_egress == "residential" and self.residential_proxy is None:
            raise ValueError(
                "RESIDENTIAL_PROXY must be configured when DOWNLOAD_EGRESS=residential"
            )
        return self

    def residential_proxy_url(self) -> str:
        """Return the configured proxy only for use by the downloader process."""
        if self.residential_proxy is None:
            raise RuntimeError("Residential proxy is not configured")
        return self.residential_proxy.get_secret_value()


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
