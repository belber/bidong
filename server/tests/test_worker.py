from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Binding, RobotCursor, User
from app.robot.worker import process_at, process_follow, run_once
from app.services.activation import bind, issue_activation
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


def _seed_follow_since(db, ts):
    cursor = db.query(RobotCursor).filter(RobotCursor.kind == "follow_since").first()
    if cursor is None:
        cursor = RobotCursor(
            kind="follow_since", last_id="", last_time=ts, updated_at=utcnow_naive()
        )
        db.add(cursor)
    else:
        cursor.last_time = ts
    db.commit()
    return cursor


def test_process_follow_first_run_skips_existing(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    client = FakeClient(followers=[{"mid": "111", "uname": "A", "mtime": 1700000000}])

    process_follow(db, client)

    assert client.sent == []
    cursor = db.query(RobotCursor).filter(RobotCursor.kind == "follow_since").one()
    assert cursor.last_time > 0
    db.close()


def test_process_follow_sends_only_after_baseline(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    _seed_follow_since(db, 1700000000)
    client = FakeClient(
        followers=[
            {"mid": "111", "uname": "A", "mtime": 1699999999},
            {"mid": "222", "uname": "B", "mtime": 1700000001},
        ]
    )

    process_follow(db, client)

    assert [uid for uid, _ in client.sent] == ["222"]
    assert db.query(Binding).filter(Binding.bili_uid == "111").count() == 0
    binding = db.query(Binding).filter(Binding.bili_uid == "222").one()
    assert client.sent == [("222", f"壁咚激活码：{binding.activation_code}")]
    db.close()


def test_process_follow_does_not_resend(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    _seed_follow_since(db, 1700000000)
    client = FakeClient(followers=[{"mid": "222", "uname": "B", "mtime": 1700000001}])

    process_follow(db, client)
    process_follow(db, client)

    assert len(client.sent) == 1
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


def test_run_once_runs_both_loops(db_engine):
    settings.robot_send_interval_seconds = 0
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    _seed_follow_since(db, 1700000000)
    client = FakeClient(
        followers=[{"mid": "222", "uname": "B", "mtime": 1700000001}],
        at=[],
    )

    run_once(db, client)

    assert len(client.sent) == 1
    assert db.query(Binding).filter(Binding.bili_uid == "222").count() == 1
    db.close()
