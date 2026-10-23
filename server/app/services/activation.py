import secrets
import uuid

from sqlalchemy.orm import Session

from ..config import settings
from ..errors import AppError
from ..models import Binding
from ..time import utcnow_naive

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REVIEWER_BILI_NAME = "微信审核专用"


def generate_code(length: int = 10) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def _reviewer_codes() -> set[str]:
    raw = settings.reviewer_activation_codes or ""
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def _bind_reviewer(db: Session, user_id: int, code: str) -> Binding:
    """审核码可复用：同一个码给每个微信用户各建一条审核绑定。

    每个用户的绑定用 `<审核码>-<user_id>` 做唯一激活码，bili_uid 用随机
    audit-review-* 占位，避免撞上 `activation_code` / `bili_uid` 的唯一约束。
    同一用户重复提交直接返回已有审核绑定，不报“已使用”。
    """
    existing = db.query(Binding).filter(Binding.user_id == user_id).first()
    if existing is not None:
        # 兼容历史审核绑定（activation_code 就是审核码本身）和新的 per-user 码
        if (existing.activation_code or "") == code or (
            existing.activation_code or ""
        ).startswith(code + "-"):
            return existing
        raise AppError(400, "该账号已绑定过 B站账号")

    per_user_code = f"{code}-{user_id}"[:32]
    binding = (
        db.query(Binding)
        .filter(Binding.activation_code == per_user_code)
        .first()
    )
    if binding is None:
        binding = Binding(
            bili_uid="audit-review-" + uuid.uuid4().hex[:12],
            bili_name=REVIEWER_BILI_NAME,
            activation_code=per_user_code,
            created_at=utcnow_naive(),
        )
        db.add(binding)
    binding.user_id = user_id
    binding.bound_at = utcnow_naive()
    db.commit()
    db.refresh(binding)
    return binding


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

    if normalized in _reviewer_codes():
        return _bind_reviewer(db, user_id, normalized)

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
