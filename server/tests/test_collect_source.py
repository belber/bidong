import tempfile

import respx
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import User
from app.services.collect import collect_video, collect_video_by_bvid
from app.time import utcnow_naive
from helpers import BVID, mock_bili


def _make_user(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    user = User(openid="robot-test-user", created_at=utcnow_naive())
    db.add(user)
    db.commit()
    db.refresh(user)
    return db, user


@respx.mock
def test_collect_video_defaults_to_local(db_engine):
    mock_bili()
    settings.storage_backend = "local"
    settings.local_storage_dir = tempfile.mkdtemp()
    settings.public_base_url = "http://testserver"

    db, user = _make_user(db_engine)
    card, *_ = collect_video(db, user, f"https://www.bilibili.com/video/{BVID}")
    assert card.source == "local"
    db.close()


@respx.mock
def test_collect_video_by_bvid_source_robot(db_engine):
    mock_bili()
    settings.storage_backend = "local"
    settings.local_storage_dir = tempfile.mkdtemp()
    settings.public_base_url = "http://testserver"

    db, user = _make_user(db_engine)
    card, *_ = collect_video_by_bvid(db, user, BVID, source="robot")
    assert card.source == "robot"
    db.close()
