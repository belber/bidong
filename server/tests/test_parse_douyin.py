"""POST /api/parse 按平台分流。网络全用 respx 打桩。"""

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.services import config_store
from app.services.douyin_provider import DETAIL_API

FIXTURE = Path(__file__).parent / "fixtures" / "douyin_detail_video.json"
AWEME_ID = "7685688911658323392"
COVER_URL_PREFIX = "https://p26-sign.douyinpic.com"


@pytest.fixture(autouse=True)
def _with_douyin_cookie(db_engine):
    """没配会话时 provider 会直接快速失败，这些用例要的是解析本身。"""
    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)()
    config_store.set_douyin_cookie(db, "sessionid=x; sid_tt=x; uid_tt=x")
    db.commit()
    db.close()


def _mock_douyin():
    respx.get(DETAIL_API).mock(
        return_value=httpx.Response(200, content=FIXTURE.read_bytes())
    )
    respx.get(url__startswith=COVER_URL_PREFIX).mock(
        return_value=httpx.Response(
            200, content=b"\xff\xd8\xff\xe0cover", headers={"content-type": "image/jpeg"}
        )
    )


@respx.mock
def test_parse_douyin_video(client, auth_headers):
    _mock_douyin()
    resp = client.post(
        "/api/parse",
        json={"url": f"https://www.douyin.com/video/{AWEME_ID}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["platform"] == "douyin"
    assert data["bvid"] == AWEME_ID
    assert data["title"] == "给我39个粉丝更新一下#萌妹子 #男高"
    assert data["up_name"] == "Dustinsuperstar"
    # 结果页「抖音号」那一行读的是 author_id；原来后端没暴露它，前端永远是空的
    assert data["author_id"] == "74305918298"
    assert data["partition"] == ""  # 抖音没有分区
    assert data["duration"] == 13
    assert data["source_url"] == f"https://www.douyin.com/video/{AWEME_ID}"
    assert data["cover_url"].endswith(".jpg")
    assert sorted(data["tags"]) == ["男高", "萌妹子"]

    # 数据卡：第 4 格走 share，不是 coin
    assert data["stats"]["like"] == 15931
    assert data["stats"]["reply"] == 1553
    assert data["stats"]["favorite"] == 1521
    assert data["stats"]["share"] == 2887
    assert data["stats"]["coin"] == 0

    # 媒体：一条无水印视频 + 一条音频，没有图文
    assert data["media"]["clean"] is True
    assert data["media"]["watermarked"] is False
    assert data["media"]["audio"] is True
    assert data["media"]["images"] == 0

    # 没有文本类内容，前端整块不渲染
    assert data["subtitles"] == []
    assert data["danmaku_count"] == 0
    assert data["features"] == {"comment": False, "danmaku": False}
    assert data["origin"] is None


@respx.mock
def test_parse_douyin_is_idempotent(client, auth_headers):
    _mock_douyin()
    first = client.post(
        "/api/parse",
        json={"url": f"https://www.douyin.com/video/{AWEME_ID}"},
        headers=auth_headers,
    ).json()
    second = client.post(
        "/api/parse",
        json={"url": f"https://www.douyin.com/video/{AWEME_ID}"},
        headers=auth_headers,
    ).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/cards", headers=auth_headers).json()) == 1


@respx.mock
def test_parse_douyin_session_dead_reports_clearly(client, auth_headers):
    respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=b""))
    resp = client.post(
        "/api/parse",
        json={"url": f"https://www.douyin.com/video/{AWEME_ID}"},
        headers=auth_headers,
    )
    assert resp.status_code == 503
    body = resp.json()
    # 前端只该看到统一维护提示，不该看到会话/Cookie 这类内部术语
    assert body["message"] == "管理员正在解决中，请稍后再试"
    assert "会话" not in body["message"]
    assert "Cookie" not in body["message"]
    assert body["error_type"] == "douyin_session_invalid"


@respx.mock
def test_parse_douyin_note_marks_images(client, auth_headers):
    detail = json.loads(FIXTURE.read_text(encoding="utf-8"))["aweme_detail"]
    detail["images"] = [
        {"url_list": [f"{COVER_URL_PREFIX}/note1.jpeg"]},
        {"url_list": [f"{COVER_URL_PREFIX}/note2.jpeg"]},
    ]
    respx.get(DETAIL_API).mock(
        return_value=httpx.Response(200, content=json.dumps({"aweme_detail": detail}).encode())
    )
    respx.get(url__startswith=COVER_URL_PREFIX).mock(
        return_value=httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})
    )
    resp = client.post(
        "/api/parse",
        json={"url": f"https://www.douyin.com/note/{AWEME_ID}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["media"]["images"] == 2
    assert data["source_url"].endswith(f"/note/{AWEME_ID}")


def test_parse_unknown_link_still_400(client, auth_headers):
    resp = client.post("/api/parse", json={"url": "https://example.com/x"}, headers=auth_headers)
    assert resp.status_code == 400
