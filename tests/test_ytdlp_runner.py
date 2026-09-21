from app import ytdlp_runner
from yt_dlp.networking._helper import make_socks_proxy_opts


def test_residential_wrapper_preserves_socks5_local_dns():
    proxies = {"all": "socks5://100.77.149.28:1080"}

    ytdlp_runner.clean_proxies_preserving_socks5(proxies, {})

    assert proxies["all"] == "socks5://100.77.149.28:1080"
    assert make_socks_proxy_opts(proxies["all"])["rdns"] is False


def test_residential_wrapper_patches_ytdlp_import_sites():
    ytdlp_runner.configure_socks5_local_dns()

    from yt_dlp.YoutubeDL import clean_proxies

    assert clean_proxies is ytdlp_runner.clean_proxies_preserving_socks5
