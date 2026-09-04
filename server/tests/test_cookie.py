from sqlalchemy.orm import sessionmaker

from app.errors import AppError
from app.robot import cookie
from app.services import config_store


def _db(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    return Session()


class FakeClient:
    def __init__(self, info=None, error=None):
        self.info = info
        self.error = error
        self.closed = False

    def get_self_info(self):
        if self.error:
            raise self.error
        return self.info

    def close(self):
        self.closed = True


def test_check_cookie_valid_first_time_no_alert(db_engine, monkeypatch):
    monkeypatch.setattr(cookie, "build_client", lambda *a, **k: FakeClient(info={"isLogin": True}))
    sent = []
    monkeypatch.setattr(cookie.notify, "send_alert_email", lambda *a, **k: sent.append(a))
    db = _db(db_engine)

    result = cookie.check_cookie(db)

    assert result["cookie_valid"] is True
    assert sent == []
    assert config_store.cookie_status(db)["cookie_last_checked"]
    db.close()


def test_check_cookie_transition_sends_alert(db_engine, monkeypatch):
    monkeypatch.setattr(cookie, "build_client", lambda *a, **k: FakeClient(info={"isLogin": True}))
    db = _db(db_engine)
    # 先记录一次有效检测
    cookie.check_cookie(db)

    monkeypatch.setattr(
        cookie,
        "build_client",
        lambda *a, **k: FakeClient(error=AppError(502, "B站机器人接口请求失败")),
    )
    sent = []
    monkeypatch.setattr(cookie.notify, "send_alert_email", lambda *a, **k: sent.append(a))

    result = cookie.check_cookie(db)

    assert result["cookie_valid"] is False
    assert len(sent) == 1
    db.close()
