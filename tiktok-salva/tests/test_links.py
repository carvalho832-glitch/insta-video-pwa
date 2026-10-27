import pytest
from app import normalize_link

@pytest.mark.parametrize("url", [
    "https://www.tiktok.com/@fulano/video/7345678901234567890",
    "https://vm.tiktok.com/ZMabcdefgh/",
    "https://vt.tiktok.com/ZMabcdefgh/",
    "Confira: https://www.tiktok.com/t/ZMabcdefgh/?foo=bar",
])
def test_valid(url):
    final, _ = normalize_link(url)
    assert final.startswith("https://")
    assert "?" not in final

@pytest.mark.parametrize("url", [
    "http://www.tiktok.com/@user/video/7345678901234567890",
    "https://www.tiktok.com.evil.org/@user/video/7345678901234567890",
    "https://www.tiktok.com/@user",
    "https://www.tiktok.com:8443/@user/video/7345678901234567890",
    "https://127.0.0.1/video/7345678901234567890",
])
def test_invalid(url):
    with pytest.raises(ValueError):
        normalize_link(url)
