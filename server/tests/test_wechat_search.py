"""搜一搜数据推送：换 access_token、组装页面、推送与错误翻译。"""

import httpx
import respx
from sqlalchemy.orm import sessionmaker

from app.services import wechat_search

TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
PUSH_URL = "https://api.weixin.qq.com/wxa/search/wxaapi_submitpages"


def _db(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)()


def _seed_card(db, **over):
    from app.models import User, VideoCard

    payload = {
        "bvid": "BV1Nse466EsX",
        "title": "【小视频】167-国贸街拍",
        "up_name": "帅哥录屏",
        "partition": "旅游出行",
        "duration": 106,
        "pubdate": 1789796701,
        "cover_url": "https://cos.example/bv.jpg",
        "desc": "YouTube 街拍",
        "source_url": "https://www.bilibili.com/video/BV1Nse466EsX",
    }
    payload.update(over)

    user = db.query(User).first()
    if user is None:
        user = User(openid="openid-1")
        db.add(user)
        db.commit()
        db.refresh(user)

    card = VideoCard(
        user_id=user.id,
        bvid=payload["bvid"],
        title=payload["title"],
        cover_url=payload["cover_url"],
        up_name=payload["up_name"],
        partition=payload["partition"],
        desc=payload["desc"],
        source_url=payload["source_url"],
        duration=payload["duration"],
        pubdate=payload["pubdate"],
        up_mid="3707052465589015",  # 白名单账号，出处才会带出来
        month="2026-09",
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@respx.mock
def test_access_token_is_cached(db_engine, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "wechat_appid", "wxapp")
    monkeypatch.setattr(settings, "wechat_secret", "secret")
    route = respx.get(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "TOKEN-1", "expires_in": 7200}
        )
    )
    db = _db(db_engine)
    assert wechat_search.get_access_token(db) == "TOKEN-1"
    assert wechat_search.get_access_token(db) == "TOKEN-1"
    assert route.call_count == 1  # 第二次走缓存，不再打微信
    db.close()


@respx.mock
def test_access_token_error_is_clear(db_engine, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "wechat_appid", "wxapp")
    monkeypatch.setattr(settings, "wechat_secret", "bad")
    respx.get(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"errcode": 40013, "errmsg": "invalid appid"}
        )
    )
    db = _db(db_engine)
    try:
        wechat_search.get_access_token(db)
        raise AssertionError("应该抛错")
    except wechat_search.SearchPushError as exc:
        assert "40013" in str(exc)
    db.close()


def test_build_page_payload_has_required_fields(db_engine):
    db = _db(db_engine)
    card = _seed_card(db)
    page = wechat_search.build_video_page(db, card, "wxsearch_testcpdata")
    assert page["path"] == "pages/result/result"
    assert page["query"] == "bvid=BV1Nse466EsX"
    item = page["data_list"][0]
    assert item["@type"] == "wxsearch_testcpdata"
    assert item["update"] == 1
    assert item["content_id"] == "BV1Nse466EsX"
    assert item["page_type"] == 2
    assert item["title"]
    assert len(item["title"]) <= 20
    assert item["mainbody"] and "<" not in item["mainbody"]  # 正文不能带 html
    assert item["cover_img_url"].startswith("http")
    assert item["time_publish"] == card.pubdate
    assert item["time_modify"] > 0
    db.close()


def test_build_page_includes_origin_in_mainbody(db_engine):
    db = _db(db_engine)
    card = _seed_card(db)
    from app.services import repost_source

    repost_source.upsert_items(
        db,
        [
            {
                "bvid": card.bvid,
                "platform": "douyin",
                "author_name": "李不然",
                "author_handle": "luke0123",
            }
        ],
    )
    page = wechat_search.build_video_page(db, card, "wxsearch_cpdata")
    body = page["data_list"][0]["mainbody"]
    assert "李不然" in body
    assert "抖音" in body
    db.close()


@respx.mock
def test_submit_pages_maps_wechat_errors(db_engine, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "wechat_appid", "wxapp")
    monkeypatch.setattr(settings, "wechat_secret", "secret")
    respx.get(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "T", "expires_in": 7200})
    )
    respx.post(PUSH_URL).mock(
        return_value=httpx.Response(
            200, json={"errcode": 85091, "errmsg": "search status was turned off"}
        )
    )
    db = _db(db_engine)
    try:
        wechat_search.submit_pages(
            db,
            [{"path": "pages/result/result", "query": "bvid=BV1", "data_list": [{}]}],
        )
        raise AssertionError("应该抛错")
    except wechat_search.SearchPushError as exc:
        # 错误码要翻译成人话，方便运营直接知道去后台点哪里
        assert "开关" in str(exc) and "85091" in str(exc)
    db.close()


@respx.mock
def test_push_videos_records_state(db_engine, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "wechat_appid", "wxapp")
    monkeypatch.setattr(settings, "wechat_secret", "secret")
    respx.get(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "T", "expires_in": 7200})
    )
    sent = {}

    def _capture(request):
        sent["body"] = request.content.decode()
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    respx.post(PUSH_URL).mock(side_effect=_capture)

    db = _db(db_engine)
    _seed_card(db)
    result = wechat_search.push_videos(db, mode="audit")
    assert result["ok"] == 1
    assert result["fail"] == 0
    assert "wxsearch_testcpdata" in sent["body"]

    state = wechat_search.state(db)
    assert state["last_push_at"]
    assert state["last_ok"] == 1
    db.close()


@respx.mock
def test_maybe_push_search_respects_switch_and_daily_limit(db_engine, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "wechat_appid", "wxapp")
    monkeypatch.setattr(settings, "wechat_secret", "secret")
    respx.get(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "T", "expires_in": 7200})
    )
    route = respx.post(PUSH_URL).mock(
        return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
    )

    db = _db(db_engine)
    _seed_card(db)

    # 开关关着：什么都不做
    assert wechat_search.maybe_push_search(db) is False
    assert route.call_count == 0

    wechat_search.set_enabled(db, True)
    assert wechat_search.maybe_push_search(db) is True
    assert route.call_count == 1
    # 同一天不会再推第二次
    assert wechat_search.maybe_push_search(db) is False
    assert route.call_count == 1
    db.close()


def test_admin_search_status_and_push(admin_client, db_engine, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "wechat_appid", "wxapp")
    monkeypatch.setattr(settings, "wechat_secret", "secret")
    token = admin_client.post(
        "/api/admin/login", json={"password": "admin-dev-password"}
    ).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    status = admin_client.get("/api/admin/search/status", headers=auth).json()
    assert status["enabled"] is False
    assert status["mode"] == "audit"

    updated = admin_client.put(
        "/api/admin/search/config",
        json={"enabled": True, "mode": "prod"},
        headers=auth,
    ).json()
    assert updated["enabled"] is True
    assert updated["mode"] == "prod"

    # 推送失败时要把微信的错误原样告诉运营（这里没配 appid 之外的东西，走真实调用会失败）
    failed = admin_client.post(
        "/api/admin/search/push", json={"scope": "new"}, headers=auth
    )
    assert failed.status_code in (200, 400)
