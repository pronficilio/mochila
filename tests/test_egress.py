from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from app import downloader
from app.settings import Settings, settings


def valid_job() -> dict[str, str]:
    return {
        "id": "egress-test-job",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "mode": "video",
        "max_height": "1080",
        "audio_format": "m4a",
    }


def configure_direct(monkeypatch) -> None:
    monkeypatch.setattr(settings, "download_egress", "direct")
    monkeypatch.setattr(settings, "residential_proxy", None)


def configure_residential(monkeypatch, proxy: str) -> None:
    monkeypatch.setattr(settings, "download_egress", "residential")
    monkeypatch.setattr(settings, "residential_proxy", SecretStr(proxy))


def test_direct_does_not_add_proxy(monkeypatch):
    configure_direct(monkeypatch)

    command = downloader.build_command(valid_job())

    assert "--proxy" not in command
    assert "--force-ipv4" not in command


def test_residential_adds_exact_configured_proxy(monkeypatch):
    proxy = "socks5://100.64.0.10:1080"
    configure_residential(monkeypatch, proxy)

    command = downloader.build_command(valid_job())

    proxy_index = command.index("--proxy")
    assert command[proxy_index + 1] == proxy
    assert command[proxy_index - 1] == "--force-ipv4"


def test_residential_without_proxy_fails_validation():
    with pytest.raises(ValidationError, match="RESIDENTIAL_PROXY must be configured"):
        Settings(
            _env_file=None,
            app_password="test-password",
            download_egress="residential",
        )


def test_empty_proxy_is_allowed_for_direct_and_rejected_for_residential():
    direct = Settings(
        _env_file=None,
        app_password="test-password",
        download_egress="direct",
        residential_proxy="",
    )
    assert direct.residential_proxy is None

    with pytest.raises(ValidationError, match="RESIDENTIAL_PROXY must be configured"):
        Settings(
            _env_file=None,
            app_password="test-password",
            download_egress="residential",
            residential_proxy="",
        )


@pytest.mark.parametrize("proxy", [
    "http://100.64.0.10:1080",
    "https://100.64.0.10:1080",
    "socks5h://100.64.0.10:1080",
])
def test_non_residential_proxy_schemes_are_rejected(proxy):
    with pytest.raises(ValidationError, match="must use socks5://"):
        Settings(
            _env_file=None,
            app_password="test-password",
            download_egress="residential",
            residential_proxy=proxy,
        )


def test_invalid_proxy_configuration_error_redacts_credentials():
    proxy = "https://user:password@100.64.0.10:1080"

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            app_password="test-password",
            download_egress="residential",
            residential_proxy=proxy,
        )

    assert "user:password" not in str(error.value)
    assert proxy not in str(error.value)


def test_socks5_proxy_scheme_is_accepted():
    proxy = "socks5://100.64.0.10:1080"
    configured = Settings(
        _env_file=None,
        app_password="test-password",
        download_egress="residential",
        residential_proxy=proxy,
    )

    assert configured.residential_proxy_url() == proxy


def test_proxy_credentials_do_not_appear_in_errors_or_representation(monkeypatch):
    proxy = "socks5://user:password@100.64.0.10:1080"
    configure_residential(monkeypatch, proxy)
    monkeypatch.setattr(downloader, "residential_proxy_reachable", lambda: True)
    monkeypatch.setattr(
        downloader.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=f"failed to connect through {proxy}",
        ),
    )

    with pytest.raises(downloader.DownloadError) as error:
        downloader.run_download(valid_job())

    assert "user:password" not in str(error.value)
    assert proxy not in str(error.value)
    assert "user:password" not in repr(settings.residential_proxy)


def test_residential_unreachable_fails_closed_without_starting_ytdlp(monkeypatch):
    configure_residential(monkeypatch, "socks5://100.64.0.10:1080")
    monkeypatch.setattr(downloader, "residential_proxy_reachable", lambda: False)

    def should_not_run(*args, **kwargs):
        raise AssertionError("yt-dlp must not run without residential egress")

    monkeypatch.setattr(downloader.subprocess, "run", should_not_run)

    with pytest.raises(
        downloader.DownloadError, match="Residential egress is unavailable"
    ):
        downloader.run_download(valid_job())


def test_command_is_argv_list_not_a_shell_command(monkeypatch):
    configure_residential(monkeypatch, "socks5://100.64.0.10:1080")

    command = downloader.build_command(valid_job())

    assert isinstance(command, list)
    assert command[-2:] == ["--", valid_job()["url"]]
    assert all(isinstance(argument, str) for argument in command)
