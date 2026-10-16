"""media-size：结果页每个下载项旁边那行「约 xx MB」。

抖音的视频大小直接用 detail 里的 `play_addr.data_size`（解析流程本来就取过一次 detail，
不再多发请求）；音频的 `play_url` 不带大小，只能 HEAD 一次 CDN 读 `Content-Length`。

大小是展示信息：任何一步拿不到都只是不显示，不能让接口报错。
"""

import json
from pathlib import Path

import httpx
import respx
from sqlalchemy.orm import sessionmaker

from app.models import User, VideoCard
from app.services import config_store
from app.services.douyin_provider import DETAIL_API
from app.time import utcnow_naive

FIXTURE = Path(__file__).parent / "fixtures" / "douyin_detail_video.json"
AWEME_ID = "7685688911658323392"

DETAIL = json.loads(FIXTURE.read_text(encoding="utf-8"))
VIDEO_URL = DETAIL["aweme_detail"]["video"]["play_addr"]["url_list"][0]
AUDIO_URL = DETAIL["aweme_detail"]["music"]["play_url"]["url_list"][0]
VIDEO_BYTES = DETAIL["aweme_detail"]["video"]["play_addr"]["data_size"]
AUDIO_BYTES = 3_000_000


def _seed_card(db_engine, platform="douyin"):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    # 没有配置会话时 provider 会直接快速失败，不会发请求
    config_store.set_douyin_cookie(db, "sessionid=x; sid_tt=x; uid_tt=x")
    db.commit()
    user = db.query(User).filter(User.openid == "dev_user1").first()
    if user is None:
        user = User(openid="dev_user1")
        db.add(user)
        db.commit()
    card = VideoCard(
        user_id=user.id,
        platform=platform,
        bvid=AWEME_ID,
        title="t",
        cover_url="",
        up_name="u",
        partition="",
        desc="",
        source_url=f"https://www.douyin.com/video/{AWEME_ID}",
        source="local",
        collected_at=utcnow_naive(),
        month="2026-10",
    )
    db.add(card)
    db.commit()
    card_id = card.id
    db.close()
    return card_id


def _mock_detail(payload=None, content=None):
    body = content if content is not None else json.dumps(payload or DETAIL).encode()
    respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=body))


def _mock_audio_size(size=AUDIO_BYTES, status=200):
    headers = {"Content-Length": str(size)} if size else {}
    for method in (respx.head, respx.get):
        method(AUDIO_URL).mock(return_value=httpx.Response(status, headers=headers))


@respx.mock
def test_video_size_comes_from_detail_data_size(client, auth_headers, db_engine):
    """视频大小就写在 detail 里，不需要再问 CDN 一次。"""
    _mock_detail()
    _mock_audio_size()
    card_id = _seed_card(db_engine)

    data = client.get(f"/api/cards/{card_id}/media-size", headers=auth_headers).json()

    assert data["video"] == VIDEO_BYTES
    assert data["audio"] == AUDIO_BYTES


@respx.mock
def test_video_size_falls_back_to_head_when_detail_has_no_size(client, auth_headers, db_engine):
    """老响应可能没有 data_size，那时退回问 CDN。"""
    detail = json.loads(json.dumps(DETAIL))
    detail["aweme_detail"]["video"]["play_addr"].pop("data_size")
    _mock_detail(detail)
    _mock_audio_size()
    respx.head(VIDEO_URL).mock(
        return_value=httpx.Response(200, headers={"Content-Length": "1504900"})
    )
    card_id = _seed_card(db_engine)

    data = client.get(f"/api/cards/{card_id}/media-size", headers=auth_headers).json()

    assert data["video"] == 1504900


@respx.mock
def test_cdn_without_length_only_drops_that_key(client, auth_headers, db_engine):
    """CDN 不回长度时不显示这一行的大小，接口照常 200。"""
    _mock_detail()
    _mock_audio_size(size=0, status=405)
    card_id = _seed_card(db_engine)

    resp = client.get(f"/api/cards/{card_id}/media-size", headers=auth_headers)

    assert resp.status_code == 200
    assert "audio" not in resp.json()
    assert resp.json()["video"] == VIDEO_BYTES


@respx.mock
def test_disabled_switches_skip_the_work(client, auth_headers, db_engine, monkeypatch):
    """开关关掉就不该再去取数——连 detail 都不请求。"""
    card_id = _seed_card(db_engine)

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    config_store.set_douyin_switches(db, video=False, audio=False)
    db.commit()
    db.close()

    def _boom(*args, **kwargs):
        raise AssertionError("开关关掉了还去请求抖音")

    monkeypatch.setattr("app.services.douyin_provider.DouyinProvider.fetch_detail", _boom)

    data = client.get(f"/api/cards/{card_id}/media-size", headers=auth_headers).json()

    assert data == {}


@respx.mock
def test_session_invalid_falls_back_to_empty(client, auth_headers, db_engine):
    """身份失效时抖音回 200 + 0 字节：没有大小可显示，但不是接口错误。"""
    _mock_detail(content=b"")
    card_id = _seed_card(db_engine)

    resp = client.get(f"/api/cards/{card_id}/media-size", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {}


@respx.mock
def test_bilibili_keys_unchanged(client, auth_headers, db_engine, monkeypatch):
    """B站 分支的键名和口径不动：watermarked / clean / audio。"""
    card_id = _seed_card(db_engine, platform="bilibili")

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    config_store.set_media_switches(db, True, True, True)
    db.commit()
    db.close()

    def _fake_streams(client, card, kind):
        return [{"qn": 80, "url": f"https://cdn.bilivideo.com/{kind}.mp4", "backup_urls": []}]

    monkeypatch.setattr("app.routers.media._streams", _fake_streams)
    for kind in ("watermarked", "clean", "audio"):
        respx.head(f"https://cdn.bilivideo.com/{kind}.mp4").mock(
            return_value=httpx.Response(200, headers={"Content-Length": "2000000"})
        )

    data = client.get(f"/api/cards/{card_id}/media-size", headers=auth_headers).json()

    assert data == {"watermarked": 2000000, "clean": 2000000, "audio": 2000000}
