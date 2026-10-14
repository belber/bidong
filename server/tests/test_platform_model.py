"""平台字段：同一用户可以在两个平台各留一张卡片，互不冲突。"""

import respx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import DownloadEvent, ParseLog, User, VideoCard
from app.time import utcnow_naive


def _session(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)()


def _card(user_id: int, platform: str | None, bvid: str) -> VideoCard:
    """platform=None 表示不显式传，用来验证默认值。"""
    kwargs = dict(
        user_id=user_id,
        bvid=bvid,
        title="t",
        cover_url="",
        up_name="u",
        partition="",
        desc="",
        source_url="https://example.com",
        source="local",
        collected_at=utcnow_naive(),
        month="2026-10",
    )
    if platform is not None:
        kwargs["platform"] = platform
    return VideoCard(**kwargs)


def test_card_defaults_to_bilibili(db_engine):
    db = _session(db_engine)
    user = User(openid="openid-platform")
    db.add(user)
    db.commit()

    card = _card(user.id, None, "BV1xx411c7mD")
    db.add(card)
    db.commit()
    assert card.platform == "bilibili"
    db.close()


def test_same_id_allowed_across_platforms(db_engine):
    """抖音作品 ID 是纯数字，理论上可能和 BV 号撞不了，但约束必须按平台拆开。"""
    db = _session(db_engine)
    user = User(openid="openid-platform2")
    db.add(user)
    db.commit()

    db.add(_card(user.id, "bilibili", "7685688911658323392"))
    db.add(_card(user.id, "douyin", "7685688911658323392"))
    db.commit()

    count = db.query(VideoCard).filter(VideoCard.user_id == user.id).count()
    assert count == 2
    db.close()


def test_same_id_same_platform_still_rejected(db_engine):
    db = _session(db_engine)
    user = User(openid="openid-platform3")
    db.add(user)
    db.commit()

    db.add(_card(user.id, "douyin", "7685688911658323392"))
    db.commit()

    db.add(_card(user.id, "douyin", "7685688911658323392"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    else:  # pragma: no cover - 约束失效才会走到这里
        raise AssertionError("同一平台同一作品应当被唯一约束挡住")
    db.close()


def test_parse_log_and_download_event_carry_platform(db_engine):
    db = _session(db_engine)
    db.add(ParseLog(platform="douyin", source="local", input="x", ok=True))
    db.add(DownloadEvent(platform="douyin", bvid="7685688911658323392", stage="resolve", status="success"))
    db.commit()

    assert db.query(ParseLog).one().platform == "douyin"
    assert db.query(DownloadEvent).one().platform == "douyin"
    db.close()


def test_log_platform_defaults_to_bilibili(db_engine):
    db = _session(db_engine)
    db.add(ParseLog(source="local", input="x", ok=True))
    db.add(DownloadEvent(bvid="BV1xx411c7mD", stage="resolve", status="success"))
    db.commit()

    assert db.query(ParseLog).one().platform == "bilibili"
    assert db.query(DownloadEvent).one().platform == "bilibili"
    db.close()


@respx.mock
def test_bilibili_parse_does_not_reuse_douyin_card(client, auth_headers, db_engine):
    """bvid 列两个平台共用，查卡片时必须带 platform，否则会串号。"""
    from helpers import BVID, mock_bili

    mock_bili()
    db = _session(db_engine)
    user = db.query(User).filter(User.openid == "dev_user1").first()
    if user is None:
        user = User(openid="dev_user1")
        db.add(user)
        db.commit()
    db.add(_card(user.id, "douyin", BVID))
    db.commit()
    db.close()

    resp = client.post(
        "/api/parse",
        json={"url": f"https://www.bilibili.com/video/{BVID}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["platform"] == "bilibili"

    db = _session(db_engine)
    rows = db.query(VideoCard).all()
    assert sorted(r.platform for r in rows) == ["bilibili", "douyin"]
    db.close()
