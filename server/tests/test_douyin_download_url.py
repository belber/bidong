"""抖音 download-url：现取直链、候选、域名登记、图文多图不去重。"""

import json
from pathlib import Path

import httpx
import respx
from sqlalchemy.orm import sessionmaker

import pytest

from app.config import settings
from app.models import BiliCdnDomain, User, VideoCard
from app.services.douyin_provider import DETAIL_API
from app.time import utcnow_naive

FIXTURE = Path(__file__).parent / "fixtures" / "douyin_detail_video.json"
AWEME_ID = "7685688911658323392"


@pytest.fixture(autouse=True)
def _real_candidates(monkeypatch):
    """本地 .env 开了 DOWNLOAD_DEBUG_FAIL（返回必然失败的调试候选），测试里关掉。"""
    monkeypatch.setattr(settings, "download_debug_fail", False)


def _seed_card(db_engine, platform="douyin"):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
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


def _mock_detail(payload=None):
    body = payload if payload is not None else json.loads(FIXTURE.read_text(encoding="utf-8"))
    respx.get(DETAIL_API).mock(
        return_value=httpx.Response(200, content=json.dumps(body).encode())
    )


@respx.mock
def test_video_candidates_are_deduped_by_host(client, auth_headers, db_engine):
    _mock_detail()
    card_id = _seed_card(db_engine)
    resp = client.get(
        f"/api/cards/{card_id}/download-url", params={"kind": "video"}, headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "video"
    assert len(data["candidates"]) >= 1
    hosts = [c["host"] for c in data["candidates"]]
    assert len(hosts) == len(set(hosts))  # 同一个文件的多 CDN，按域名去重
    assert all(c["url"].startswith("http") for c in data["candidates"])
    assert all(c["configured"] is False for c in data["candidates"])  # 还没登记


@respx.mock
def test_domains_get_recorded(client, auth_headers, db_engine):
    _mock_detail()
    card_id = _seed_card(db_engine)
    client.get(f"/api/cards/{card_id}/download-url", params={"kind": "video"}, headers=auth_headers)

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    hosts = [r.host for r in db.query(BiliCdnDomain).all()]
    assert any(h.endswith("douyinvod.com") for h in hosts)
    db.close()


@respx.mock
def test_configured_domain_is_flagged(client, auth_headers, db_engine):
    _mock_detail()
    card_id = _seed_card(db_engine)

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(BiliCdnDomain(host="v81-cold.douyinvod.com", is_configured=True, seen_count=1))
    db.commit()
    db.close()

    data = client.get(
        f"/api/cards/{card_id}/download-url", params={"kind": "video"}, headers=auth_headers
    ).json()
    assert any(c["configured"] for c in data["candidates"])


@respx.mock
def test_audio_kind(client, auth_headers, db_engine):
    _mock_detail()
    card_id = _seed_card(db_engine)
    data = client.get(
        f"/api/cards/{card_id}/download-url", params={"kind": "audio"}, headers=auth_headers
    ).json()
    assert data["candidates"]
    assert data["candidates"][0]["host"].endswith("douyinstatic.com")


@respx.mock
def test_images_return_all_without_dedup(client, auth_headers, db_engine):
    detail = json.loads(FIXTURE.read_text(encoding="utf-8"))["aweme_detail"]
    same_host = "https://p26-sign.douyinpic.com"
    detail["images"] = [
        {"url_list": [f"{same_host}/a.jpeg"]},
        {"url_list": [f"{same_host}/b.jpeg"]},
        {"url_list": [f"{same_host}/c.jpeg"]},
    ]
    _mock_detail({"aweme_detail": detail})
    card_id = _seed_card(db_engine)

    data = client.get(
        f"/api/cards/{card_id}/download-url", params={"kind": "image"}, headers=auth_headers
    ).json()
    # 图文不去重：同域名下三张图都要给前端
    assert len(data["candidates"]) == 3
    assert [c["url"].rsplit("/", 1)[-1] for c in data["candidates"]] == [
        "a.jpeg", "b.jpeg", "c.jpeg"
    ]


@respx.mock
def test_unknown_kind_rejected(client, auth_headers, db_engine):
    _mock_detail()
    card_id = _seed_card(db_engine)
    resp = client.get(
        f"/api/cards/{card_id}/download-url", params={"kind": "danmaku"}, headers=auth_headers
    )
    assert resp.status_code == 400


@respx.mock
def test_switch_off_blocks_download(client, auth_headers, db_engine):
    _mock_detail()
    card_id = _seed_card(db_engine)
    from app.services import config_store

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    config_store.set_douyin_switches(db, video=False)
    db.commit()
    db.close()

    resp = client.get(
        f"/api/cards/{card_id}/download-url", params={"kind": "video"}, headers=auth_headers
    )
    assert resp.status_code == 403


@respx.mock
def test_session_dead_surfaces_clearly(client, auth_headers, db_engine):
    respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=b""))
    card_id = _seed_card(db_engine)
    resp = client.get(
        f"/api/cards/{card_id}/download-url", params={"kind": "video"}, headers=auth_headers
    )
    assert resp.status_code == 502
    assert "会话" in resp.json()["message"]
