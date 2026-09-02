import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import Binding, RobotCursor


def test_binding_user_id_nullable_and_bili_uid_unique(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(Binding(bili_uid="111", activation_code="ABC123"))
    db.commit()

    binding = db.query(Binding).filter(Binding.bili_uid == "111").one()
    assert binding.user_id is None
    assert binding.bound_at is None

    db.add(Binding(bili_uid="111", activation_code="XYZ999"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()


def test_robot_cursor_kind_unique(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(RobotCursor(kind="follow", last_time=0))
    db.commit()

    cursor = db.query(RobotCursor).filter(RobotCursor.kind == "follow").one()
    assert cursor.last_time == 0
    db.close()
