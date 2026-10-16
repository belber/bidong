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


def test_stores_douyin_id_not_sec_uid(db, meta):
    """up_mid 存抖音号（用户能搜到人），不是 sec_uid（主页链接里那串超长 ID）。

    线上踩过：sec_uid 有 77 字符，up_mid 是 VARCHAR(32)，PostgreSQL 直接
    StringDataRightTruncation 导致整次解析 500。
    """
    card = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=_cover_fetcher)
    assert card.up_mid == meta.author_unique_id == "74305918298"
    assert card.up_mid != meta.author_sec_uid
    assert len(meta.author_sec_uid) > 32  # 就是它超长


def test_every_string_field_fits_its_column(db, meta):
    """SQLite 不校验 VARCHAR 长度、PostgreSQL 校验，本地测试抓不到超长。

    这里按列定义手工校验一遍，把「本地全绿、线上 500」挡在提交前。
    """
    card = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=_cover_fetcher)
    for column in VideoCard.__table__.columns:
        limit = getattr(column.type, "length", None)
        value = getattr(card, column.name, None)
        if limit and isinstance(value, str):
            assert len(value) <= limit, f"{column.name} 超长：{len(value)} > {limit}"


def test_long_author_name_is_clamped(db, meta):
    """昵称超过列宽时裁掉，而不是让整次解析 500。"""
    meta.author_name = "很长的昵称" * 60  # 300 字
    card = collect_douyin.collect_douyin(db, _user(db), meta, fetch_cover=_cover_fetcher)
    assert len(card.up_name) <= VideoCard.__table__.columns["up_name"].type.length


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
