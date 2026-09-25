from sqlalchemy.orm import sessionmaker

from app.services import config_store, repost_source

UP_MID = "3707052465589015"
BVID = "BV15Pbj6yEKg"


def _db(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    return Session()


def _record(db, bvid=BVID, **over):
    repost_source.upsert_items(
        db,
        [
            {
                "bvid": bvid,
                "title": "【小视频】126-减脂只是为了多吃",
                "platform": "douyin",
                "author_name": "小山坡",
                "author_url": "https://www.douyin.com/user/MS4w",
                **over,
            }
        ],
    )


def test_origin_complete_when_channel_and_record_match(db_engine):
    db = _db(db_engine)
    _record(db)
    origin = repost_source.get_origin(db, bvid=BVID, up_mid=UP_MID)
    assert origin is not None
    assert origin.account_name == "帅哥录屏"
    assert origin.platform == "douyin"
    assert origin.platform_label == "抖音"
    assert origin.author_name == "小山坡"
    assert origin.author_url == "https://www.douyin.com/user/MS4w"
    db.close()


def test_origin_present_but_empty_when_channel_matches_without_record(db_engine):
    """台账漏记过的稿件也要显示区块，只是内容为空（前端显示「整理中」）。"""
    db = _db(db_engine)
    origin = repost_source.get_origin(db, bvid=BVID, up_mid=UP_MID)
    assert origin is not None
    assert origin.platform_label == ""
    assert origin.author_name == ""
    assert origin.account_name == "帅哥录屏"
    db.close()


def test_origin_none_for_other_up(db_engine):
    db = _db(db_engine)
    _record(db)
    assert repost_source.get_origin(db, bvid=BVID, up_mid="123456789") is None
    db.close()


def test_origin_none_when_up_mid_missing(db_engine):
    db = _db(db_engine)
    _record(db)
    assert repost_source.get_origin(db, bvid=BVID, up_mid="") is None
    assert repost_source.get_origin(db, bvid=BVID, up_mid=None) is None
    db.close()


def test_origin_none_when_whitelist_empty(db_engine):
    db = _db(db_engine)
    _record(db)
    config_store.set_repost_config(db, up_mid="")
    assert repost_source.get_origin(db, bvid=BVID, up_mid=UP_MID) is None
    db.close()


def test_whitelist_supports_multiple_mids(db_engine):
    db = _db(db_engine)
    _record(db)
    config_store.set_repost_config(db, up_mid=f"111, {UP_MID}, 222")
    assert repost_source.is_repost_channel(db, UP_MID) is True
    assert repost_source.is_repost_channel(db, 111) is True
    assert repost_source.is_repost_channel(db, 333) is False
    db.close()


def test_account_name_and_avatar_come_from_config(db_engine):
    db = _db(db_engine)
    config_store.set_repost_config(
        db, account_name="帅哥录屏备用号", account_avatar_url="https://cos/avatar.jpg"
    )
    origin = repost_source.get_origin(db, bvid=BVID, up_mid=UP_MID)
    assert origin.account_name == "帅哥录屏备用号"
    assert origin.account_avatar_url == "https://cos/avatar.jpg"
    db.close()


def test_platform_label_mapping():
    assert repost_source.platform_label("douyin") == "抖音"
    assert repost_source.platform_label("DOUYIN") == "抖音"
    assert repost_source.platform_label("x") == "X"
    assert repost_source.platform_label("youtube") == "YouTube"
    assert repost_source.platform_label("unknown") == ""
    assert repost_source.platform_label("") == ""
    # 未登记的平台原样展示，不要吞掉信息
    assert repost_source.platform_label("weishi") == "weishi"


def test_summary_counts(db_engine):
    db = _db(db_engine)
    _record(db, bvid="BV1txaT6nEz3")
    repost_source.upsert_items(
        db, [{"bvid": "BV18paT6pE7Y", "platform": "douyin", "note": "parse失败 404"}]
    )
    result = repost_source.summary(db)
    assert result["total"] == 2
    assert result["with_author"] == 1
    assert result["without_author"] == 1
    assert result["last_updated_at"] is not None
    db.close()
