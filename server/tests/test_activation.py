import pytest

from app.errors import AppError
from app.models import Binding
from app.services.activation import bind, generate_code, issue_activation


def test_generate_code_shape_and_uniqueness():
    codes = {generate_code() for _ in range(100)}
    assert all(len(c) == 10 and c.isalnum() for c in codes)
    assert len(codes) > 90


def test_issue_activation_idempotent_per_uid(db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    first = issue_activation(db, "111")
    second = issue_activation(db, "111")
    assert first.id == second.id
    assert first.activation_code == second.activation_code
    assert db.query(Binding).filter(Binding.bili_uid == "111").count() == 1
    db.close()


def test_issue_activation_stores_and_backfills_name(db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    first = issue_activation(db, "555", "壁咚菌")
    assert first.bili_name == "壁咚菌"

    first.bili_name = ""
    db.commit()

    again = issue_activation(db, "555", "壁咚菌")
    assert again.bili_name == "壁咚菌"
    db.close()


def test_bind_success_and_single_use(db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    issued = issue_activation(db, "222")
    bound = bind(db, 7, issued.activation_code)
    assert bound.user_id == 7
    assert bound.bound_at is not None

    with pytest.raises(AppError):
        bind(db, 8, issued.activation_code)
    with pytest.raises(AppError):
        bind(db, 9, "NOT-A-CODE")
    db.close()


def test_bind_rejects_second_account_for_same_user(db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    first = issue_activation(db, "333")
    second = issue_activation(db, "444")
    bind(db, 11, first.activation_code)

    with pytest.raises(AppError):
        bind(db, 11, second.activation_code)
    db.close()
