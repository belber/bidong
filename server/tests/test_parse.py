import respx

from helpers import BVID, mock_bili


@respx.mock
def test_parse_auto_collect_and_idempotent(client, auth_headers):
    mock_bili()
    resp = client.post(
        "/api/parse",
        json={"url": f"https://www.bilibili.com/video/{BVID}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    first = resp.json()
    assert first["bvid"] == BVID
    assert first["title"] == "测试标题"
    assert first["cover_url"].endswith(".jpg")
    assert set(first["tags"]) == {"科幻", "深度"}
    assert first["source"] == "local"
    assert first["month"]
    assert [s["text"] for s in first["subtitles"]] == ["第一句", "第二句"]
    assert first["subtitles"][0]["t"] == 5
    assert first["stats"] == {"like": 111, "reply": 22, "favorite": 333, "coin": 44}
    assert first["danmaku_count"] == 55
    assert first["media"] == {"watermarked": False, "clean": False, "audio": False}

    again = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]

    cards = client.get("/api/cards", headers=auth_headers).json()
    assert len(cards) == 1


@respx.mock
def test_parse_invalid_url(client, auth_headers):
    resp = client.post("/api/parse", json={"url": "https://example.com/abc"}, headers=auth_headers)
    assert resp.status_code == 400
