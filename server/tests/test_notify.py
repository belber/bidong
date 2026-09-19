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
