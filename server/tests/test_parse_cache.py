import respx

from app.services.parse_cache import ParseCache
from helpers import BVID, mock_bili


def test_cache_get_set_and_clear():
    cache = ParseCache(ttl_seconds=60)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    cache.clear()
    assert cache.get("k") is None


def test_cache_expires():
    cache = ParseCache(ttl_seconds=0)
    cache.set("k", "v")
    assert cache.get("k") is None


@respx.mock
def test_parse_uses_cache_for_same_bvid(client, auth_headers):
    mock_bili()
    first = client.post(
        "/api/parse",
        json={"url": f"https://www.bilibili.com/video/{BVID}"},
        headers=auth_headers,
    )
    assert first.status_code == 200

    def view_calls():
        return [c for c in respx.calls if "x/web-interface/view" in str(c.request.url)]

    assert len(view_calls()) == 1

    # 不同的链接形态，但同一个 bvid，也应命中缓存
    second = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    # 第二次命中缓存，不应再请求 B站 view 接口
    assert len(view_calls()) == 1


@respx.mock
def test_parse_cache_refreshes_switches_on_hit(client, auth_headers, monkeypatch):
    from app.config import settings

    mock_bili()
    first = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["features"]["danmaku"] is True

    # 关闭弹幕开关后，即使第二次命中缓存，开关也应实时生效
    monkeypatch.setattr(settings, "enable_danmaku", False)
    again = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert again.status_code == 200
    assert again.json()["features"]["danmaku"] is False
