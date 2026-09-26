"""微信搜索爬虫访问的识别、记录与汇总。"""

import hashlib
from datetime import timedelta

from sqlalchemy.orm import sessionmaker

from app.models import CrawlerVisit
from app.services import crawler
from app.time import utcnow_naive


def _db(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)()


def test_looks_like_crawler_by_user_agent():
    assert crawler.looks_like_crawler({"user-agent": "mpcrawler"}) is True
    assert crawler.looks_like_crawler({"user-agent": "Mozilla/5.0 mpcrawler/1.0"}) is True
    assert crawler.looks_like_crawler({"user-agent": "MicroMessenger/8.0"}) is False
    # 指南里说爬虫还会带这三个头，认出来就行
    assert crawler.looks_like_crawler({"x-wxapp-crawler-signature": "abc"}) is True
    assert crawler.looks_like_crawler({}) is False


def test_verify_signature_follows_wechat_rule():
    token, ts, nonce = "tok", "1700000000", "abc"
    raw = "".join(sorted([token, ts, nonce]))
    signature = hashlib.sha1(raw.encode()).hexdigest()
    assert crawler.verify_signature(token, ts, nonce, signature) is True
    assert crawler.verify_signature(token, ts, nonce, "wrong") is False
    # 没配 Token 时无法校验，返回 None（而不是当成假爬虫）
    assert crawler.verify_signature("", ts, nonce, signature) is None


def test_record_and_summary(db_engine):
    db = _db(db_engine)
    crawler.record(
        db,
        source="scene",
        path="pages/result/result",
        query="bvid=BV1Nse466EsX",
        scene=1129,
        verified=None,
    )
    crawler.record(
        db,
        source="scene",
        path="pages/home/home",
        scene=1129,
        verified=None,
        created_at=utcnow_naive() - timedelta(days=3),
    )
    crawler.record(
        db,
        source="header",
        path="/api/public/cards/BV1Nse466EsX",
        user_agent="mpcrawler",
        verified=True,
    )

    summary = crawler.summary(db)
    assert summary["total"] == 3
    assert summary["today"] == 2
    assert summary["last_seen"]
    assert summary["verified"] == 1
    assert summary["unverified"] == 0
    by_path = {row["path"]: row["count"] for row in summary["by_path"]}
    assert by_path["pages/result/result"] == 1
    db.close()


def test_public_crawler_report_endpoint(client, db_engine):
    resp = client.post(
        "/api/public/crawler-visit",
        json={"path": "pages/home/home", "query": "", "scene": 1129},
    )
    assert resp.status_code == 200
    db = _db(db_engine)
    row = db.query(CrawlerVisit).one()
    assert row.source == "scene"
    assert row.path == "pages/home/home"
    assert row.scene == 1129
    db.close()


def test_admin_crawler_stats_requires_token(admin_client):
    assert admin_client.get("/api/admin/stats/crawler").status_code == 401

    login = admin_client.post("/api/admin/login", json={"password": "admin-dev-password"})
    resp = admin_client.get(
        "/api/admin/stats/crawler",
        headers={"Authorization": f"Bearer {login.json()['token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "today" in body and "total" in body and "by_path" in body
    assert "items" in body
