import httpx
import respx

from helpers import BVID, mock_bili


def _playurl_video(qn=64):
    return httpx.Response(
        200,
        json={
            "code": 0,
            "data": {
                "dash": {
                    "video": [
                        {"id": qn, "baseUrl": "https://v.example.com/v.m4s", "backupUrl": []}
                    ],
                    "audio": [
                        {"id": 30280, "baseUrl": "https://a.example.com/a.m4s", "backupUrl": []}
                    ],
                }
            },
        },
    )


def _mock_playurl():
    respx.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*fnval=16.*").mock(
        return_value=_playurl_video()
    )
    respx.get("https://v.example.com/v.m4s").mock(
        return_value=httpx.Response(200, content=b"video-bytes")
    )
    respx.get("https://a.example.com/a.m4s").mock(
        return_value=httpx.Response(200, content=b"audio-bytes")
    )


def _make_card(client, auth_headers):
    mock_bili()
    resp = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()


@respx.mock
def test_media_options_disabled_by_default(client, auth_headers, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_clean_video", False)
    card = _make_card(client, auth_headers)
    resp = client.get(
        f"/api/cards/{card['id']}/media-options",
        params={"kind": "clean"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


@respx.mock
def test_media_options_and_download(client, auth_headers, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_clean_video", True)
    _mock_playurl()
    card = _make_card(client, auth_headers)

    opts = client.get(
        f"/api/cards/{card['id']}/media-options",
        params={"kind": "clean"},
        headers=auth_headers,
    )
    assert opts.status_code == 200
    assert opts.json() == [{"qn": 64, "label": "720P"}]

    resp = client.get(
        f"/api/cards/{card['id']}/download",
        params={"kind": "clean", "qn": 64},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.content == b"video-bytes"


@respx.mock
def test_danmaku_and_export(client, auth_headers):
    respx.get("https://comment.bilibili.com/987654.xml").mock(
        return_value=httpx.Response(200, text="<i><d>哈哈</d></i>")
    )
    card = _make_card(client, auth_headers)

    dm = client.get(f"/api/cards/{card['id']}/danmaku", headers=auth_headers)
    assert dm.status_code == 200
    assert "哈哈" in dm.text

    txt = client.get(
        f"/api/cards/{card['id']}/export",
        params={"kind": "txt"},
        headers=auth_headers,
    )
    assert txt.status_code == 200
    assert "测试标题" in txt.text
    assert "第一句" in txt.text
    assert "哈哈" in txt.text

    srt = client.get(
        f"/api/cards/{card['id']}/export",
        params={"kind": "srt"},
        headers=auth_headers,
    )
    assert srt.status_code == 200
    assert "00:00:05,000 --> 00:00:07,000" in srt.text
    assert "第一句" in srt.text
