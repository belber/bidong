import json

import httpx
import respx
from sqlalchemy.orm import sessionmaker

from app.services import config_store
from app.services.douyin_note_api import DtkNoteClient, dtk_content_to_detail
from app.services.douyin_provider import DETAIL_API

AWEME_ID = "7300000000000000000"
BASE = "https://dtk.example"
NOTE_URL = f"https://www.douyin.com/note/{AWEME_ID}"

CONTENT = {
    "platform": "douyin",
    "content_id": AWEME_ID,
    "kind": "image_album",
    "web_url": NOTE_URL,
    "title": "图文标题",
    "description": "图文简介 #旅行",
    "created_at": "2026-10-21T08:00:00Z",
    "duration_ms": 0,
    "author": {
        "platform": "douyin",
        "uid": "MS4wSecUid",
        "sec_uid": "MS4wSecUid",
        "unique_id": "douyin_handle",
        "nickname": "作者昵称",
    },
    "stats": {
        "digg_count": 12,
        "comment_count": 3,
        "share_count": 2,
        "collect_count": 4,
    },
    "media": {
        "covers": [{"url": "https://p3.douyinpic.com/cover.jpeg", "urls": []}],
        "video": None,
        "streams": [],
        "images": [
            {
                "url": "https://p3.douyinpic.com/preview~tplv.jpeg",
                "urls": [
                    "https://p3.douyinpic.com/original.jpeg",
                    "https://p3.douyinpic.com/preview~tplv.jpeg",
                ],
            },
            {
                "url": "https://p3.douyinpic.com/second.jpeg",
                "urls": [],
            },
        ],
    },
    "music": {"play_url": "https://music.example/a.mp3"},
    "tags": ["旅行"],
    "fetched_at": "2026-10-21T08:00:01Z",
}


@respx.mock
def test_dtk_note_client_sync_success_maps_images():
    route = respx.post(f"{BASE}/api/v1/parse").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "data": CONTENT, "error": None, "meta": {}},
        )
    )
    client = DtkNoteClient(BASE, "dtk_test_key", wait_seconds=7, poll_interval=0)
    try:
        detail = client.fetch_detail(AWEME_ID)
    finally:
        client.close()

    assert route.called
    request = route.calls[0].request
    assert request.headers["X-API-Key"] == "dtk_test_key"
    assert request.url.params["wait"] == "7"
    assert json.loads(request.content)["url"] == NOTE_URL
    assert detail["aweme_type"] == 68
    assert detail["author"]["nickname"] == "作者昵称"
    assert detail["images"][0]["url_list"] == [
        "https://p3.douyinpic.com/original.jpeg"
    ]
    assert len(detail["images"]) == 2


@respx.mock
def test_dtk_note_client_polls_202_task():
    respx.post(f"{BASE}/api/v1/parse").mock(
        return_value=httpx.Response(
            202,
            json={
                "success": True,
                "data": {"task_id": "task-1", "state": "running"},
                "error": None,
                "meta": {},
            },
        )
    )
    task_route = respx.get(f"{BASE}/api/v1/tasks/task-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {"task_id": "task-1", "state": "done", "data": CONTENT},
                "error": None,
                "meta": {},
            },
        )
    )
    client = DtkNoteClient(BASE, "dtk_test_key", wait_seconds=1, poll_interval=0)
    try:
        detail = client.fetch_detail(AWEME_ID)
    finally:
        client.close()
    assert task_route.called
    assert len(detail["images"]) == 2


def test_dtk_content_to_detail_uses_plain_title_first_line():
    content = dict(CONTENT)
    content["title"] = "第一行标题"
    content["description"] = "第一行标题\n第二行正文"
    detail = dtk_content_to_detail(content)
    assert detail["desc"] == "第一行标题\n第二行正文"
    assert detail["music"]["play_url"]["url_list"] == ["https://music.example/a.mp3"]


@respx.mock
def test_parse_note_uses_configured_third_party_api(client, auth_headers, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    config_store.set_douyin_cookie(db, "sessionid=x; sid_tt=x; uid_tt=x")
    config_store.set_douyin_note_api_config(
        db,
        enabled=True,
        base_url=BASE,
        api_key="dtk_test_key",
        wait_seconds=5,
    )
    db.close()

    mobile = {
        "status_code": 0,
        "filter_detail": {"filter_reason": "images_base"},
        "aweme_detail": {},
    }
    respx.get(DETAIL_API).mock(
        return_value=httpx.Response(200, content=json.dumps(mobile).encode())
    )
    respx.post(f"{BASE}/api/v1/parse").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "data": CONTENT, "error": None, "meta": {}},
        )
    )
    respx.get(url__startswith="https://p3.douyinpic.com").mock(
        return_value=httpx.Response(200, content=b"jpeg", headers={"content-type": "image/jpeg"})
    )

    resp = client.post(
        "/api/parse",
        json={"url": NOTE_URL},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["media"]["note"] is True
    assert data["media"]["images"] == 2
    # 沿用现有抖音口径：卡片标题取作品文案，而不是 DTK 的首行 title。
    assert data["title"] == "图文简介 #旅行"

    download = client.get(
        f"/api/cards/{data['id']}/download-url",
        params={"kind": "image"},
        headers=auth_headers,
    )
    assert download.status_code == 200
    candidates = download.json()["candidates"]
    assert len(candidates) == 2
    assert candidates[0]["url"] == "https://p3.douyinpic.com/original.jpeg"
