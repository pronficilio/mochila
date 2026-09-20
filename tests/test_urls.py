import pytest
from app.urls import validate_youtube_url


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
])
def test_valid(url):
    assert validate_youtube_url(url) == url


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "http://127.0.0.1:8080/admin",
    "https://youtube.com.evil.example/watch?v=x",
    "https://example.com/video",
])
def test_rejects_non_youtube(url):
    with pytest.raises(ValueError):
        validate_youtube_url(url)
