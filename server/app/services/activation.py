import secrets

from sqlalchemy.orm import Session

from ..errors import AppError
from ..models import Binding
from ..time import utcnow_naive

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code(length: int = 10) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def issue_activation(db: Session, bili_uid: str, bili_name: str = "") -> Binding:
    bili_uid = str(bili_uid)
    name = (bili_name or "").strip()
    existing = db.query(Binding).filter(Binding.bili_uid == bili_uid).first()
    if existing is not None:
        if name and not (existing.bili_name or "").strip():
            existing.bili_name = name
            db.commit()
            db.refresh(existing)
        return existing

    binding = Binding(
        bili_uid=bili_uid,
        bili_name=name,
        activation_code=generate_code(),
        created_at=utcnow_naive(),
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding


def bind(db: Session, user_id: int, code: str) -> Binding:
    normalized = (code or "").strip().upper()
    if not normalized:
        raise AppError(400, "激活码无效")

    binding = db.query(Binding).filter(Binding.activation_code == normalized).first()
    if binding is None:
        raise AppError(400, "激活码无效")
    if binding.bound_at is not None or binding.user_id is not None:
        raise AppError(400, "激活码已使用")

    already = db.query(Binding).filter(Binding.user_id == user_id).first()
    if already is not None:
        raise AppError(400, "该账号已绑定过 B站账号")

    binding.user_id = user_id
    binding.bound_at = utcnow_naive()
    db.commit()
    db.refresh(binding)
    return binding


def unbind(db: Session, user_id: int) -> None:
    binding = db.query(Binding).filter(Binding.user_id == user_id).first()
    if binding is not None:
        binding.user_id = None
        binding.bound_at = None
        db.commit()
