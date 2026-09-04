from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import AdminConfig
from app.services import config_store as cs


def _db(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    return Session()


def test_get_raw_defaults_to_none(db_engine):
    db = _db(db_engine)
    assert cs.get_raw(db, "missing", default=None) is None
    db.close()


def test_set_and_get_raw_roundtrip(db_engine):
    db = _db(db_engine)
    cs.set_raw(db, "enable_audio", "true")
    assert cs.get_raw(db, "enable_audio") == "true"
    cs.set_raw(db, "enable_audio", "false")
    assert cs.get_raw(db, "enable_audio") == "false"
    assert db.query(AdminConfig).filter(AdminConfig.key == "enable_audio").count() == 1
    db.close()


def test_typed_getters(db_engine):
    db = _db(db_engine)
    cs.set_raw(db, "at_poll_interval", "42")
    assert cs.get_int(db, "at_poll_interval") == 42
    assert cs.get_bool(db, "cookie_valid", default=True) is True
    cs.set_raw(db, "cookie_valid", "no")
    assert cs.get_bool(db, "cookie_valid", default=True) is False
    db.close()


def test_media_switches_fall_back_to_env(db_engine):
    db = _db(db_engine)
    switches = cs.media_switches(db)
    assert switches["watermarked"] is settings.enable_watermarked_video
    cs.set_media_switches(db, True, False, True)
    switches = cs.media_switches(db)
    assert switches == {"watermarked": True, "clean": False, "audio": True}
    db.close()


def test_parse_switches_fall_back_to_env_and_roundtrip(db_engine):
    db = _db(db_engine)
    switches = cs.parse_switches(db)
    assert switches["comment"] is settings.enable_comment
    assert switches["danmaku"] is settings.enable_danmaku

    cs.set_parse_switches(db, False, True)
    assert cs.parse_switches(db) == {"comment": False, "danmaku": True}
    db.close()


def test_robot_guide_roundtrip(db_engine):
    db = _db(db_engine)
    assert cs.robot_guide_enabled(db) is settings.enable_robot_guide
    cs.set_robot_guide_enabled(db, False)
    assert cs.robot_guide_enabled(db) is False
    db.close()


def test_share_roundtrip(db_engine):
    db = _db(db_engine)
    assert cs.share_enabled(db) is settings.enable_share
    cs.set_share_enabled(db, False)
    assert cs.share_enabled(db) is False
    db.close()


def test_robot_cookie_merges_env_and_db(db_engine):
    db = _db(db_engine)
    cookie = cs.robot_cookie(db)
    assert cookie["SESSDATA"] == settings.robot_sessdata

    cs.set_robot_cookie(db, {"SESSDATA": "db-value", "robot_uid": "999"})
    cookie = cs.robot_cookie(db)
    assert cookie["SESSDATA"] == "db-value"
    assert cookie["robot_uid"] == "999"
    assert cookie["bili_jct"] == settings.robot_bili_jct  # 未覆盖的用 env
    db.close()


def test_schedule_roundtrip_and_defaults(db_engine):
    db = _db(db_engine)
    sched = cs.schedule(db)
    assert sched["follow_window"] == settings.robot_follow_window_seconds
    cs.set_schedule(db, at_poll_interval=60, follow_window=900)
    sched = cs.schedule(db)
    assert sched["at_poll_interval"] == 60
    assert sched["follow_window"] == 900
    assert sched["follow_poll_interval"] == settings.robot_poll_interval_seconds
    db.close()


def test_alert_config_roundtrip(db_engine):
    db = _db(db_engine)
    cfg = cs.alert_config(db)
    assert cfg["alert_enabled"] is settings.alert_enabled
    cs.set_alert_config(db, alert_enabled=True, alert_email="a@b.com", smtp_port=587)
    cfg = cs.alert_config(db)
    assert cfg["alert_enabled"] is True
    assert cfg["alert_email"] == "a@b.com"
    assert cfg["smtp_port"] == 587
    db.close()


def test_cookie_status_roundtrip(db_engine):
    db = _db(db_engine)
    status = cs.cookie_status(db)
    assert status["cookie_valid"] is True
    cs.set_cookie_status(db, valid=False, last_checked="2026-09-03T10:00", last_error="expired")
    status = cs.cookie_status(db)
    assert status["cookie_valid"] is False
    assert status["cookie_last_error"] == "expired"
    db.close()


def test_seed_defaults_persists_and_does_not_overwrite(db_engine, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_watermarked_video", True)
    monkeypatch.setattr(settings, "robot_follow_window_seconds", 999)
    db = _db(db_engine)
    # 预置一个用户已保存的值
    cs.set_raw(db, "enable_audio", "true")

    cs.seed_defaults(db)

    # 缺失的键取自 env
    assert cs.media_switches(db)["watermarked"] is True
    assert cs.get_int(db, "follow_window") == 999
    # 已存在的键不被覆盖
    assert cs.get_bool(db, "enable_audio", default=False) is True
    db.close()


def test_help_config_default_empty_and_roundtrip(db_engine):
    db = _db(db_engine)
    assert cs.get_help_config(db) == {"qq_group": ""}
    cs.set_help_config(db, "123456789")
    assert cs.get_help_config(db) == {"qq_group": "123456789"}
    cs.set_help_config(db, "  ")
    assert cs.get_help_config(db) == {"qq_group": ""}
    db.close()
