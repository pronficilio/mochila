"""Run yt-dlp while preserving SOCKS5 local DNS resolution.

yt-dlp intentionally rewrites socks5:// to socks5h:// for legacy compatibility.
Mochila's residential topology needs the opposite: resolve IPv4 on the worker and
send that address through the residential SOCKS tunnel.
"""

import importlib
import sys
import urllib.parse
import urllib.request

from yt_dlp.utils import remove_start


def clean_proxies_preserving_socks5(proxies: dict, headers: object) -> None:
    """Equivalent to yt-dlp's cleaner without its socks5 -> socks5h rewrite."""
    request_proxy = headers.pop("Ytdl-Request-Proxy", None)
    if request_proxy:
        proxies.clear()
        proxies["all"] = request_proxy

    for proxy_key, proxy_url in proxies.items():
        if proxy_url == "__noproxy__":
            proxies[proxy_key] = None
            continue
        if proxy_key == "no" or proxy_url is None:
            continue
        try:
            proxy_scheme = urllib.request._parse_proxy(proxy_url)[0]
        except ValueError:
            continue
        if proxy_scheme is None:
            proxies[proxy_key] = "http://" + remove_start(proxy_url, "//")
        elif proxy_scheme == "socks":
            proxies[proxy_key] = urllib.parse.urlunparse(
                urllib.parse.urlparse(proxy_url)._replace(scheme="socks4")
            )


def configure_socks5_local_dns() -> None:
    """Patch yt-dlp modules that imported the legacy proxy cleaner directly."""
    for module_name in (
        "yt_dlp.utils.networking",
        "yt_dlp.YoutubeDL",
        "yt_dlp.extractor.youtube._video",
        "yt_dlp.extractor.youtube.jsc._builtin.deno",
        "yt_dlp.extractor.youtube.jsc._builtin.bun",
    ):
        module = importlib.import_module(module_name)
        setattr(module, "clean_proxies", clean_proxies_preserving_socks5)


def main(argv: list[str] | None = None) -> None:
    configure_socks5_local_dns()
    import yt_dlp

    yt_dlp.main(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    main()
