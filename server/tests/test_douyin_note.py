"""图文（图集）：接口能返回图片就正常用，被过滤就明确说不支持。

抖音的移动端接口对图文作品有两种可能的表现，这里都要覆盖：
  1. 只回一个 filter_detail.filter_reason = "images_base"，拿不到作品信息
  2. 回完整作品信息但 images 为空
两种情况都不能糊成「作品不可见或已被删除」——那是错的文案，用户会以为视频被删了。
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy.orm import sessionmaker

from app.errors import AppError
from app.models import User, VideoCard
from app.services import douyin
from app.services.douyin_provider import DETAIL_API, DouyinProvider
from app.time import utcnow_naive

FIXTURE = Path(__file__).parent / "fixtures" / "douyin_detail_video.json"
AWEME_ID = "7300000000000000000"
NOTE_IMAGE = "https://p26-sign.douyinpic.com/a.jpeg"


@pytest.fixture(autouse=True)
def _with_cookie(db_engine):
    """没有会话时 provider 会快速失败，这里统一配上。"""
    from sqlalchemy.orm import sessionmaker as _sm

    from app.services import config_store as _cs

    db = _sm(bind=db_engine, autoflush=False, expire_on_commit=False)()
    _cs.set_douyin_cookie(db, "sessionid=x; sid_tt=x; uid_tt=x")
    db.commit()
    db.close()


def _note_detail(*, with_images: bool) -> dict:
    detail = json.loads(FIXTURE.read_text(encoding="utf-8"))["aweme_detail"]
    detail["aweme_id"] = AWEME_ID
    detail["aweme_type"] = 68
    detail["images"] = [{"url_list": [NOTE_IMAGE]}] if with_images else []
    return detail


@pytest.fixture
def provider():
    p = DouyinProvider(cookie="sessionid=x; sid_tt=x; uid_tt=x")
    yield p
    p.close()


class TestMetaKind:
    def test_aweme_type_68_marks_note_even_without_images(self):
        meta = douyin.meta_from_detail(_note_detail(with_images=False))
        assert meta.kind == "note"
        assert meta.image_urls == []

    def test_note_with_images_keeps_urls(self):
        meta = douyin.meta_from_detail(_note_detail(with_images=True))
        assert meta.kind == "note"
        assert meta.image_urls == [NOTE_IMAGE]

    def test_video_stays_video(self):
        detail = json.loads(FIXTURE.read_text(encoding="utf-8"))["aweme_detail"]
        assert douyin.meta_from_detail(detail).kind == "video"


class TestFilteredResponse:
    @respx.mock
    def test_filtered_note_reports_unsupported_not_missing(self, provider):
        body = {
            "status_code": 0,
            "filter_detail": {"filter_reason": "images_base", "detail_msg": "图文暂不支持"},
            "aweme_detail": {},
        }
        respx.get(DETAIL_API).mock(
            return_value=httpx.Response(200, content=json.dumps(body).encode())
        )
        with pytest.raises(AppError) as exc:
            provider.fetch_detail(AWEME_ID)
        assert exc.value.error_type == "douyin_note_unsupported"
        assert "图文" in exc.value.message
        assert "删除" not in exc.value.message

    @respx.mock
    def test_partial_detail_is_usable(self, provider):
        """有些情况下作品信息还在，只是 images 被摘掉——这种要能建卡。"""
        body = {
            "status_code": 0,
            "filter_detail": {"filter_reason": "images_base"},
            "aweme_detail": _note_detail(with_images=False),
        }
        respx.get(DETAIL_API).mock(
            return_value=httpx.Response(200, content=json.dumps(body).encode())
        )
        detail = provider.fetch_detail(AWEME_ID)
        meta = douyin.meta_from_detail(detail)
        assert meta.kind == "note"
        assert meta.image_urls == []


@respx.mock
def test_parse_note_reports_unsupported_flag(client, auth_headers):
    body = {
        "status_code": 0,
        "filter_detail": {"filter_reason": "images_base"},
        "aweme_detail": _note_detail(with_images=False),
    }
    respx.get(DETAIL_API).mock(
        return_value=httpx.Response(200, content=json.dumps(body).encode())
    )
    respx.get(url__startswith="https://p26-sign.douyinpic.com").mock(
        return_value=httpx.Response(200, content=b"jpeg", headers={"content-type": "image/jpeg"})
    )
    resp = client.post(
        "/api/parse",
        json={"url": f"https://www.douyin.com/note/{AWEME_ID}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["media"]["note"] is True
    assert data["media"]["images"] == 0
    # 建卡为图文作品，来源链接用 note 路径
    assert data["source_url"].endswith(f"/note/{AWEME_ID}")


@respx.mock
def test_parse_note_with_images_exposes_count(client, auth_headers):
    body = {"status_code": 0, "aweme_detail": _note_detail(with_images=True)}
    respx.get(DETAIL_API).mock(
        return_value=httpx.Response(200, content=json.dumps(body).encode())
    )
    respx.get(url__startswith="https://p26-sign.douyinpic.com").mock(
        return_value=httpx.Response(200, content=b"jpeg", headers={"content-type": "image/jpeg"})
    )
    data = client.post(
        "/api/parse",
        json={"url": f"https://www.douyin.com/note/{AWEME_ID}"},
        headers=auth_headers,
    ).json()
    assert data["media"]["note"] is True
    assert data["media"]["images"] == 1


@respx.mock
def test_filtered_note_parse_fails_with_clear_message(client, auth_headers):
    body = {
        "status_code": 0,
        "filter_detail": {"filter_reason": "images_base"},
        "aweme_detail": {},
    }
    respx.get(DETAIL_API).mock(
        return_value=httpx.Response(200, content=json.dumps(body).encode())
    )
    resp = client.post(
        "/api/parse",
        json={"url": f"https://www.douyin.com/note/{AWEME_ID}"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "图文" in resp.json()["message"]


@respx.mock
def test_image_download_on_unsupported_note_says_unsupported(client, auth_headers, db_engine):
    body = {
        "status_code": 0,
        "filter_detail": {"filter_reason": "images_base"},
        "aweme_detail": _note_detail(with_images=False),
    }
    respx.get(DETAIL_API).mock(
        return_value=httpx.Response(200, content=json.dumps(body).encode())
    )

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    user = db.query(User).filter(User.openid == "dev_user1").first()
    if user is None:
        user = User(openid="dev_user1")
        db.add(user)
        db.commit()
    card = VideoCard(
        user_id=user.id, platform="douyin", bvid=AWEME_ID, title="图文", cover_url="",
        up_name="u", partition="", desc="", source_url="x", source="local",
        collected_at=utcnow_naive(), month="2026-10",
    )
    db.add(card)
    db.commit()
    card_id = card.id
    db.close()

    resp = client.get(
        f"/api/cards/{card_id}/download-url", params={"kind": "image"}, headers=auth_headers
    )
    assert resp.status_code == 422
    assert "图文" in resp.json()["message"]
