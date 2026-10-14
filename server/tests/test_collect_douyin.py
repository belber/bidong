"""抖音建卡：幂等、标签、封面转存失败不拖垮解析。"""

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.models import User, VideoCard
from app.services import collect_douyin, douyin

FIXTURE = Path(__file__).parent / "fixtures" / "douyin_detail_video.json"
AWEME_ID = "7685688911658323392"
COVER = b"\xff\xd8\xff\xe0fakejpeg"


@pytest.fixture
def meta():
    detail = json.loads(FIXTURE.read_text(encoding="utf-8"))["aweme_detail"]
    return douyin.meta_from_detail(detail)


@pytest.fixture
def db(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = Session()
    session.add(User(openid="openid-dy-collect"))
    session.commit()
    yield session
    session.close()


def _user(db) -> User:
    return db.query(User).filter(User.openid == "openid-dy-collect").one()


def _cover_fetcher(url: str) -> tuple[bytes, str]:
    assert url.startswith("http")
    return COVER, "image/jpeg"


def test_creates_douyin_card(db, meta):
    card = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=_cover_fetcher)
    assert card.platform == "douyin"
    assert card.bvid == AWEME_ID
    assert card.title == meta.title
    assert card.up_name == meta.author_name
    assert card.partition == ""
    assert card.duration == meta.duration
    assert card.pubdate == meta.created_at
    assert card.source_url == f"https://www.douyin.com/video/{AWEME_ID}"
    assert card.cover_url.endswith(".jpg")
    assert sorted(t.name for t in card.tags) == ["男高", "萌妹子"]


def test_idempotent_on_reparse(db, meta):
    first = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=_cover_fetcher)
    second = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=_cover_fetcher)
    assert first.id == second.id
    assert db.query(VideoCard).count() == 1


def test_reparse_refreshes_title(db, meta):
    card = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=_cover_fetcher)
    meta.title = "改过标题"
    again = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=_cover_fetcher)
    assert again.id == card.id
    assert again.title == "改过标题"


def test_cover_failure_does_not_break_parse(db, meta):
    def boom(url: str):
        raise RuntimeError("图片 CDN 挂了")

    card = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=boom)
    assert card.bvid == AWEME_ID
    assert card.cover_url == ""


def test_note_uses_note_source_url(db, meta):
    meta.kind = "note"
    card = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=_cover_fetcher)
    assert card.source_url == f"https://www.douyin.com/note/{AWEME_ID}"


def test_same_user_can_hold_both_platforms(db, meta):
    from app.services.collect import collect_video_by_bvid  # noqa: F401  仅确认模块可导入

    card = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=_cover_fetcher)
    db.add(
        VideoCard(
            user_id=card.user_id,
            platform="bilibili",
            bvid=AWEME_ID,
            title="同 ID 的 B站 卡片",
            cover_url="",
            up_name="u",
            partition="",
            desc="",
            source_url="https://x",
            source="local",
            collected_at=card.collected_at,
            month=card.month,
        )
    )
    db.commit()
    assert db.query(VideoCard).count() == 2
