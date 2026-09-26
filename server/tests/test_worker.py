import re
import time

from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.errors import AppError
from app.models import (
    ActivationLog,
    AtEvent,
    Binding,
    FollowEvent,
    ParseLog,
    User,
)
from app.robot.worker import (
    activation_message,
    already_bound_message,
    collected_message,
    follow_guide_message,
    log_message,
    process_at,
    process_follow,
    run_once,
)
from app.services import config_store
from app.services.activation import bind, issue_activation
from app.services.tracking import classify_error
from app.time import utcnow_naive


class FakeClient:
    def __init__(self, followers=None, at=None):
        self.followers = followers or []
        self.at = at or []
        self.sent = []

    def get_followers(self):
        return self.followers

    def get_at_notifications(self):
        return self.at

    def send_msg(self, uid, content):
        self.sent.append((uid, content))


def test_process_follow_sends_recent_follower(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    client = FakeClient(
        followers=[{"mid": "222", "uname": "B", "mtime": int(time.time()) - 60}]
    )

    process_follow(db, client)

    binding = db.query(Binding).filter(Binding.bili_uid == "222").one()
    assert client.sent == [("222", activation_message(binding.activation_code))]
    db.close()


def test_process_follow_skips_old_follower(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    client = FakeClient(
        followers=[{"mid": "111", "uname": "A", "mtime": int(time.time()) - 3600}]
    )

    process_follow(db, client)

    assert client.sent == []
    assert db.query(Binding).filter(Binding.bili_uid == "111").count() == 0
    db.close()


def test_process_follow_logs_send_success(db_engine, capsys):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    client = FakeClient(
        followers=[{"mid": "222", "uname": "B", "mtime": int(time.time()) - 60}]
    )

    process_follow(db, client)

    out = capsys.readouterr().out
    assert "已向 222（B）发送激活码" in out
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ", out)
    db.close()


def test_process_follow_sends_already_bound_message_once(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    user = User(openid="bound-follow-user", created_at=utcnow_naive())
    db.add(user)
    db.commit()
    db.refresh(user)
    issued = issue_activation(db, "222", "B")
    bind(db, user.id, issued.activation_code)

    mtime = int(time.time()) - 60
    client = FakeClient(followers=[{"mid": "222", "uname": "B", "mtime": mtime}])
    process_follow(db, client)
    assert client.sent == [("222", already_bound_message())]

    client2 = FakeClient(followers=[{"mid": "222", "uname": "B", "mtime": mtime}])
    process_follow(db, client2)
    assert client2.sent == []
    db.close()


def test_process_follow_does_not_resend(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    client = FakeClient(
        followers=[{"mid": "222", "uname": "B", "mtime": int(time.time()) - 60}]
    )

    process_follow(db, client)
    process_follow(db, client)

    assert len(client.sent) == 1
    db.close()


def test_process_follow_resends_on_refollow(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    now = int(time.time())

    first = FakeClient(followers=[{"mid": "222", "uname": "B", "mtime": now - 60}])
    process_follow(db, first)
    assert len(first.sent) == 1

    # 取关后重新关注：mtime 更新为更近的时间
    second = FakeClient(followers=[{"mid": "222", "uname": "B", "mtime": now - 30}])
    process_follow(db, second)
    assert len(second.sent) == 1

    binding = db.query(Binding).filter(Binding.bili_uid == "222").one()
    assert first.sent == second.sent == [("222", activation_message(binding.activation_code))]
    db.close()


def test_process_at_collects_for_bound_and_ignores_unbound(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    user = User(openid="robot-bound-user", created_at=utcnow_naive())
    db.add(user)
    db.commit()
    db.refresh(user)

    issued = issue_activation(db, "222")
    bind(db, user.id, issued.activation_code)

    calls = []

    def fake_collect(db_, u, bvid, source):
        calls.append((u.id, bvid, source))

    client = FakeClient(
        at=[
            {"id": "1", "time": 1700000001, "mid": "222", "uname": "B", "bvid": "BV1xx411c7mD"},
            {"id": "2", "time": 1700000002, "mid": "999", "uname": "C", "bvid": "BV1yy411c7mD"},
        ]
    )

    process_at(db, client, collect=fake_collect)

    assert calls == [(user.id, "BV1xx411c7mD", "robot")]
    db.close()


def test_process_at_replies_to_unbound_user(db_engine):
    """没绑定的人 @ 我们：不回收藏、但会回私信（未关注→引导关注；已关注→重发码）。"""
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()

    # 999 从没关注过（没有 binding 行）；222 关注过但没绑定
    followed = issue_activation(db, "222", "B")
    client = FakeClient(
        at=[
            {"id": "1", "time": 1700000001, "mid": "999", "uname": "C", "bvid": "BV1yy411c7mD"},
            {"id": "2", "time": 1700000002, "mid": "222", "uname": "B", "bvid": "BV1yy411c7mD"},
        ]
    )
    process_at(db, client, collect=lambda *a, **k: None)

    assert client.sent == [
        ("999", follow_guide_message()),
        ("222", activation_message(followed.activation_code)),
    ]
    events = {e.bili_uid: e.result for e in db.query(AtEvent).all()}
    assert events["999"] == "replied_follow"
    assert events["222"] == "replied_code"
    db.close()


def test_process_at_replies_once_per_day_to_same_user(db_engine):
    """同一个人 24 小时内反复 @，只回一次（防刷屏、防风控）。"""
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    client = FakeClient(
        at=[
            {"id": "1", "time": 1700000001, "mid": "999", "uname": "C", "bvid": "BV1yy411c7mD"},
            {"id": "2", "time": 1700000002, "mid": "999", "uname": "C", "bvid": "BV1zz411c7mD"},
        ]
    )
    process_at(db, client, collect=lambda *a, **k: None)
    assert len(client.sent) == 1
    results = [e.result for e in db.query(AtEvent).order_by(AtEvent.id).all()]
    assert results == ["replied_follow", "unbound_quiet"]
    db.close()


def test_process_at_confirms_collection_for_bound_user(db_engine):
    """已绑定用户收藏成功 → 回一条确认（带视频标题），而不是静默。"""
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    user = User(openid="robot-bound-user-2", created_at=utcnow_naive())
    db.add(user)
    db.commit()
    db.refresh(user)
    issued = issue_activation(db, "333", "D")
    bind(db, user.id, issued.activation_code)

    class FakeCard:
        title = "【小视频】194-穿迷彩服过中秋"

    client = FakeClient(
        at=[{"id": "1", "time": 1700000001, "mid": "333", "uname": "D", "bvid": "BV1xx411c7mD"}]
    )
    process_at(db, client, collect=lambda *a, **k: (FakeCard(), [], {}, 0))
    assert client.sent == [("333", collected_message("【小视频】194-穿迷彩服过中秋"))]
    assert db.query(AtEvent).one().result == "replied_collected"
    db.close()


def test_process_at_keeps_quiet_when_switch_off(db_engine):
    """总开关关掉后恢复静默：只记录，不发私信。"""
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    config_store.set_at_reply_enabled(db, False)
    client = FakeClient(
        at=[{"id": "1", "time": 1700000001, "mid": "999", "uname": "C", "bvid": "BV1yy411c7mD"}]
    )
    process_at(db, client, collect=lambda *a, **k: None)
    assert client.sent == []
    assert db.query(AtEvent).one().result == "unbound"
    config_store.set_at_reply_enabled(db, True)
    db.close()


def test_run_once_runs_both_loops(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    client = FakeClient(
        followers=[{"mid": "222", "uname": "B", "mtime": int(time.time()) - 60}],
        at=[],
    )

    run_once(db, client)

    assert len(client.sent) == 1
    assert db.query(Binding).filter(Binding.bili_uid == "222").count() == 1
    db.close()


def test_process_follow_writes_follow_event_and_activation_log(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    client = FakeClient(
        followers=[{"mid": "222", "uname": "B", "mtime": int(time.time()) - 60}]
    )
    process_follow(db, client)

    event = db.query(FollowEvent).filter(FollowEvent.bili_uid == "222").one()
    assert event.sent_code is True
    assert event.bound is False

    log = db.query(ActivationLog).filter(ActivationLog.bili_uid == "222").one()
    assert log.sent_ok is True
    assert log.send_reason == ""
    db.close()


def test_process_follow_dedupes_event_by_uid_mtime(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    mtime = int(time.time()) - 60
    client = FakeClient(followers=[{"mid": "222", "uname": "B", "mtime": mtime}])
    process_follow(db, client)
    process_follow(db, client)
    assert db.query(FollowEvent).filter(FollowEvent.bili_uid == "222").count() == 1
    db.close()


def test_process_follow_logs_send_failure(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()

    class FailClient(FakeClient):
        def send_msg(self, uid, content):
            raise AppError(502, "发送私信失败：code=-101 风控")

    client = FailClient(
        followers=[{"mid": "222", "uname": "B", "mtime": int(time.time()) - 60}]
    )
    process_follow(db, client)

    log = db.query(ActivationLog).filter(ActivationLog.bili_uid == "222").one()
    assert log.sent_ok is False
    assert log.send_reason == "risk_control"
    db.close()


def test_process_at_records_unbound_and_collected_events(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    user = User(openid="robot-bound-user-2", created_at=utcnow_naive())
    db.add(user)
    db.commit()
    db.refresh(user)
    issued = issue_activation(db, "222")
    bind(db, user.id, issued.activation_code)

    calls = []

    def fake_collect(db_, u, bvid, source):
        calls.append((u.id, bvid, source))

    client = FakeClient(
        at=[
            {"id": "feed-1", "time": 1700000001, "mid": "222", "uname": "B", "bvid": "BV1xx411c7mD"},
            {"id": "feed-2", "time": 1700000002, "mid": "999", "uname": "C", "bvid": "BV1yy411c7mD"},
        ]
    )

    process_at(db, client, collect=fake_collect)

    collected = db.query(AtEvent).filter(AtEvent.feed_id == "feed-1").one()
    # 收藏成功 + 已回确认私信，合并成同一行
    assert collected.result == "replied_collected"
    unbound = db.query(AtEvent).filter(AtEvent.feed_id == "feed-2").one()
    # 没关注过 → 回引导关注（原来这里只记 unbound、什么都不发）
    assert unbound.result == "replied_follow"
    assert calls == [(user.id, "BV1xx411c7mD", "robot")]

    parse_ok = db.query(ParseLog).filter(ParseLog.source == "robot").one()
    assert parse_ok.ok is True
    assert parse_ok.bili_uid == "222"
    db.close()


def test_process_at_logs_parse_failure(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    user = User(openid="robot-bound-user-3", created_at=utcnow_naive())
    db.add(user)
    db.commit()
    db.refresh(user)
    issued = issue_activation(db, "222")
    bind(db, user.id, issued.activation_code)

    def boom(db_, u, bvid, source):
        raise AppError(502, "B站接口请求失败")

    client = FakeClient(
        at=[{"id": "feed-3", "time": 1700000003, "mid": "222", "uname": "B", "bvid": "BV1xx411c7mD"}]
    )
    process_at(db, client, collect=boom)

    event = db.query(AtEvent).filter(AtEvent.feed_id == "feed-3").one()
    assert event.result == "parse_failed"
    assert event.reason == "network_timeout"
    parse_log = db.query(ParseLog).filter(ParseLog.source == "robot").one()
    assert parse_log.ok is False
    db.close()


def test_robot_messages_do_not_contain_platform_names():
    messages = [activation_message("ABC123"), already_bound_message()]
    for message in messages:
        assert "微信" not in message
        assert "wx" not in message.lower()


def test_worker_log_message_has_beijing_timestamp():
    line = log_message("测试日志")
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} 测试日志$", line)


def test_classify_error_types():
    assert classify_error(AppError(400, "不是有效的 B站视频链接或 BV 号")) == "invalid_url"
    assert classify_error(AppError(404, "视频不存在或已被删除")) == "video_unavailable"
    assert classify_error(AppError(502, "B站接口请求失败")) == "network_timeout"
    assert classify_error(AppError(502, "封面下载失败")) == "cover_fail"
    assert classify_error(AppError(502, "转存对象存储失败")) == "storage_fail"
