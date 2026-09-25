import respx
from sqlalchemy.orm import sessionmaker

from app.models import VideoCard
from app.services import repost_source
from app.services.parse_cache import parse_cache
from helpers import BVID, mock_bili

UP_MID = "3707052465589015"


@respx.mock
def test_parse_auto_collect_and_idempotent(client, auth_headers):
    mock_bili()
    resp = client.post(
        "/api/parse",
        json={"url": f"https://www.bilibili.com/video/{BVID}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    first = resp.json()
    assert first["bvid"] == BVID
    assert first["title"] == "测试标题"
    assert first["cover_url"].endswith(".jpg")
    assert set(first["tags"]) == {"科幻", "深度"}
    assert first["source"] == "local"
    assert first["month"]
    assert [s["text"] for s in first["subtitles"]] == ["第一句", "第二句"]
    assert first["subtitles"][0]["t"] == 5
    assert first["stats"] == {"like": 111, "reply": 22, "favorite": 333, "coin": 44}
    assert first["danmaku_count"] == 55
    assert first["media"] == {"watermarked": False, "clean": False, "audio": False}

    again = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]

    cards = client.get("/api/cards", headers=auth_headers).json()
    assert len(cards) == 1


@respx.mock
def test_parse_invalid_url(client, auth_headers):
    resp = client.post("/api/parse", json={"url": "https://example.com/abc"}, headers=auth_headers)
    assert resp.status_code == 400


@respx.mock
def test_parse_backfills_partition_on_existing_card(client, db_engine, auth_headers):
    mock_bili()
    first = client.post(
        "/api/parse",
        json={"url": f"https://www.bilibili.com/video/{BVID}"},
        headers=auth_headers,
    ).json()
    assert first["partition"] == "知识"

    # 模拟历史数据：早前解析时 tname 为空，分区被存成了空字符串
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    card = db.query(VideoCard).filter(VideoCard.id == first["id"]).one()
    card.partition = ""
    db.commit()
    db.close()

    # 清缓存，确保第二次真的重新解析、走到分区回填逻辑
    parse_cache.clear()
    again = client.post("/api/parse", json={"url": BVID}, headers=auth_headers).json()
    assert again["partition"] == "知识"


@respx.mock
def test_parse_returns_feature_switches(client, auth_headers, monkeypatch):
    from app.config import settings
    from app.services.parse_cache import parse_cache

    mock_bili()
    first = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["features"] == {"comment": True, "danmaku": True}

    monkeypatch.setattr(settings, "enable_danmaku", False)
    parse_cache.clear()
    again = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert again.json()["features"] == {"comment": True, "danmaku": False}


def _add_source_record(db, bvid=BVID, **over):
    repost_source.upsert_items(
        db,
        [
            {
                "bvid": bvid,
                "platform": "douyin",
                "author_name": "小山坡",
                "author_url": "https://www.douyin.com/user/MS4w",
                **over,
            }
        ],
    )


@respx.mock
def test_parse_returns_origin_for_repost_channel(client, db_engine, auth_headers):
    mock_bili(up_mid=UP_MID)
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    _add_source_record(db)

    resp = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert resp.status_code == 200
    origin = resp.json()["origin"]
    assert origin is not None
    assert origin["account_name"] == "帅哥录屏"
    assert origin["platform_label"] == "抖音"
    assert origin["author_name"] == "小山坡"
    assert origin["author_url"] == "https://www.douyin.com/user/MS4w"

    card = db.query(VideoCard).one()
    assert card.up_mid == UP_MID
    db.close()


@respx.mock
def test_parse_origin_null_for_other_up(client, auth_headers):
    mock_bili(up_mid="99999999")
    resp = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["origin"] is None


@respx.mock
def test_parse_origin_shows_placeholder_when_channel_has_no_record(
    client, auth_headers
):
    """台账漏记过的稿件：区块要出现，但内容是空的（前端显示「整理中」）。"""
    mock_bili(up_mid=UP_MID)
    resp = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    origin = resp.json()["origin"]
    assert origin is not None
    assert origin["platform_label"] == ""
    assert origin["author_name"] == ""


@respx.mock
def test_parse_origin_is_recomputed_on_cache_hit(client, db_engine, auth_headers):
    """解析结果有 60 秒缓存，但出处不能跟着缓存变旧。"""
    mock_bili(up_mid=UP_MID)
    first = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert first.json()["origin"]["platform_label"] == ""

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    _add_source_record(db)
    db.close()

    again = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert again.status_code == 200
    assert again.json()["origin"]["platform_label"] == "抖音"
