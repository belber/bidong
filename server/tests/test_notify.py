from datetime import datetime, timezone

import httpx
import respx
from sqlalchemy.orm import sessionmaker

from app.services import config_store, notify


def _db(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)()


@respx.mock
def test_send_serverchan_posts_to_sctapi(db_engine):
    db = _db(db_engine)
    config_store.set_alert_config(db, serverchan_sendkey="SCTtestkey")
    route = respx.post("https://sctapi.ftqq.com/SCTtestkey.send").mock(
        return_value=httpx.Response(200, json={"code": 0})
    )

    assert notify.send_serverchan(db, "测试标题", "测试正文") is True
    assert route.called
    db.close()


def test_send_serverchan_without_key_returns_false(db_engine):
    db = _db(db_engine)
    assert notify.send_serverchan(db, "标题", "正文") is False
    db.close()


@respx.mock
def test_send_notification_respects_type_switch(db_engine):
    db = _db(db_engine)
    config_store.set_alert_config(
        db, serverchan_sendkey="SCTtestkey", alert_domain_enabled=False
    )
    route = respx.post("https://sctapi.ftqq.com/SCTtestkey.send").mock(
        return_value=httpx.Response(200, json={"code": 0})
    )

    sent = notify.send_notification(db, "标题", "正文", kind="domain_alert")
    assert sent == {"email": False, "serverchan": False}
    assert not route.called
    db.close()


@respx.mock
def test_send_notification_sends_serverchan(db_engine):
    db = _db(db_engine)
    config_store.set_alert_config(db, serverchan_sendkey="SCTtestkey")
    route = respx.post("https://sctapi.ftqq.com/SCTtestkey.send").mock(
        return_value=httpx.Response(200, json={"code": 0})
    )

    sent = notify.send_notification(db, "标题", "正文", kind="report")
    assert sent["serverchan"] is True
    assert route.called
    db.close()


@respx.mock
def test_fault_alert_deduplicates_same_type_and_caps_one_per_day(db_engine):
    db = _db(db_engine)
    config_store.set_alert_config(
        db,
        serverchan_sendkey="SCTtestkey",
        alert_fault_enabled=True,
    )
    route = respx.post("https://sctapi.ftqq.com/SCTtestkey.send").mock(
        return_value=httpx.Response(200, json={"code": 0})
    )
    day_one = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
    day_two = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)

    assert notify.send_fault_alert(
        db, "bilibili:bilibili_risk_control", "故障 A", "正文 A", now=day_one
    ) is True
    assert notify.send_fault_alert(
        db, "bilibili:bilibili_risk_control", "故障 A", "正文 A", now=day_one
    ) is False
    # 当天已有告警，其他故障类型也必须让路
    assert notify.send_fault_alert(
        db, "douyin:douyin_busy", "故障 B", "正文 B", now=day_one
    ) is False
    # 第二天可以发新的故障类型
    assert notify.send_fault_alert(
        db, "douyin:douyin_busy", "故障 B", "正文 B", now=day_two
    ) is True
    # 已发送过的类型永久去重
    assert notify.send_fault_alert(
        db, "bilibili:bilibili_risk_control", "故障 A", "正文 A", now=day_two
    ) is False
    assert route.call_count == 2
    db.close()


@respx.mock
def test_fault_alert_failure_does_not_consume_type_or_daily_quota(db_engine):
    db = _db(db_engine)
    config_store.set_alert_config(
        db,
        serverchan_sendkey="SCTtestkey",
        alert_fault_enabled=True,
    )
    route = respx.post("https://sctapi.ftqq.com/SCTtestkey.send").mock(
        side_effect=[
            httpx.Response(500, json={"code": 500}),
            httpx.Response(200, json={"code": 0}),
        ]
    )
    now = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)

    assert notify.send_fault_alert(
        db, "bilibili:bilibili_risk_control", "故障", "正文", now=now
    ) is False
    assert notify.send_fault_alert(
        db, "bilibili:bilibili_risk_control", "故障", "正文", now=now
    ) is True
    assert route.call_count == 2
    db.close()
