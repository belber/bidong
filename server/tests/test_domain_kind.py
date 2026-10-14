"""下载域名按类型区分：运营要优先把「视频」域名配进微信白名单。

抖音的视频、音频、图集分属三个完全不同的域名族，不区分的话运营只能瞎猜；
而微信后台的 downloadFile 合法域名有名额上限。
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import BiliCdnDomain, User, VideoCard
from app.services import media_download
from app.services.douyin_provider import DETAIL_API
from app.time import utcnow_naive

VIDEO_HOST = "v13-x.douyinvod.com"
AUDIO_HOST = "sf11-cdn-tos.douyinstatic.com"
IMAGE_HOST = "p26-sign.douyinpic.com"


@pytest.fixture(autouse=True)
def _real_candidates(monkeypatch):
    monkeypatch.setattr(settings, "download_debug_fail", False)


def _session(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)()


class TestKindCategory:
    @pytest.mark.parametrize(
        "kind,expected",
        [
            ("video", "video"),
            ("watermarked", "video"),
            ("clean", "video"),
            ("audio", "audio"),
            ("image", "image"),
            ("danmaku", ""),
            ("", ""),
        ],
    )
    def test_normalizes(self, kind, expected):
        assert media_download.kind_category(kind) == expected


class TestRecordDomain:
    def test_records_kind_on_first_sight(self, db_engine):
        db = _session(db_engine)
        media_download._record_domain(db, VIDEO_HOST, "video")
        db.commit()
        row = db.query(BiliCdnDomain).one()
        assert row.kinds == "video"
        assert row.seen_count == 1
        db.close()

    def test_accumulates_multiple_kinds(self, db_engine):
        """同一个域名服务过两种类型时不能互相覆盖。"""
        db = _session(db_engine)
        media_download._record_domain(db, VIDEO_HOST, "video")
        media_download._record_domain(db, VIDEO_HOST, "audio")
        db.commit()
        assert set(db.query(BiliCdnDomain).one().kinds.split(",")) == {"video", "audio"}
        db.close()

    def test_unknown_kind_leaves_kinds_empty(self, db_engine):
        db = _session(db_engine)
        media_download._record_domain(db, VIDEO_HOST, "danmaku")
        db.commit()
        assert db.query(BiliCdnDomain).one().kinds == ""
        db.close()


class TestAdminDomainList:
    def _auth(self, admin_client):
        token = admin_client.post(
            "/api/admin/login", json={"password": "admin-dev-password"}
        ).json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def _seed(self, db_engine):
        db = _session(db_engine)
        db.add(BiliCdnDomain(host=VIDEO_HOST, kinds="video", is_configured=False, seen_count=9))
        db.add(BiliCdnDomain(host=AUDIO_HOST, kinds="audio", is_configured=False, seen_count=99))
        db.add(BiliCdnDomain(host=IMAGE_HOST, kinds="image", is_configured=False, seen_count=5))
        db.commit()
        db.close()

    def test_filter_by_kind(self, admin_client, db_engine):
        self._seed(db_engine)
        headers = self._auth(admin_client)

        video = admin_client.get(
            "/api/admin/download/domains", params={"kind": "video"}, headers=headers
        ).json()
        assert [i["host"] for i in video["items"]] == [VIDEO_HOST]

        audio = admin_client.get(
            "/api/admin/download/domains", params={"kind": "audio"}, headers=headers
        ).json()
        assert [i["host"] for i in audio["items"]] == [AUDIO_HOST]

    def test_video_sorts_before_audio_even_with_fewer_seen(self, admin_client, db_engine):
        """视频优先：即便音频域名出现次数多得多，也要把视频排在前面。"""
        self._seed(db_engine)
        data = admin_client.get(
            "/api/admin/download/domains", headers=self._auth(admin_client)
        ).json()
        assert [i["host"] for i in data["items"]] == [VIDEO_HOST, AUDIO_HOST, IMAGE_HOST]

    def test_kind_counts_returned_for_tabs(self, admin_client, db_engine):
        self._seed(db_engine)
        data = admin_client.get(
            "/api/admin/download/domains", headers=self._auth(admin_client)
        ).json()
        assert data["kind_counts"] == {"video": 1, "image": 1, "audio": 1}

    def test_items_expose_kinds_list(self, admin_client, db_engine):
        self._seed(db_engine)
        data = admin_client.get(
            "/api/admin/download/domains", headers=self._auth(admin_client)
        ).json()
        assert data["items"][0]["kinds"] == ["video"]


@respx.mock
def test_douyin_download_records_kind(client, auth_headers, db_engine):
    """取下载地址时就要登记类型，不能等用户真下载了才有记录。"""
    fixture = Path(__file__).parent / "fixtures" / "douyin_detail_video.json"
    respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=fixture.read_bytes()))

    db = _session(db_engine)
    user = db.query(User).filter(User.openid == "dev_user1").first()
    if user is None:
        user = User(openid="dev_user1")
        db.add(user)
        db.commit()
    card = VideoCard(
        user_id=user.id,
        platform="douyin",
        bvid="7685688911658323392",
        title="t",
        cover_url="",
        up_name="u",
        partition="",
        desc="",
        source_url="x",
        source="local",
        collected_at=utcnow_naive(),
        month="2026-10",
    )
    db.add(card)
    db.commit()
    card_id = card.id
    db.close()

    client.get(
        f"/api/cards/{card_id}/download-url", params={"kind": "video"}, headers=auth_headers
    )
    client.get(
        f"/api/cards/{card_id}/download-url", params={"kind": "audio"}, headers=auth_headers
    )

    db = _session(db_engine)
    kinds = {r.host: r.kinds for r in db.query(BiliCdnDomain).all()}
    assert any(v == "video" for v in kinds.values())
    assert any(v == "audio" for v in kinds.values())
    db.close()
