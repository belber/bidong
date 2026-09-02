from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Binding, User
from ..schemas import BindingOut, BindingRequest
from ..services.activation import bind as bind_code

router = APIRouter(tags=["binding"])


@router.post("/api/binding", response_model=BindingOut)
def bind_account(
    payload: BindingRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    binding = bind_code(db, user.id, payload.code)
    return BindingOut(bound=True, bili_uid=binding.bili_uid)


@router.get("/api/binding", response_model=BindingOut)
def get_binding(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    binding = db.query(Binding).filter(Binding.user_id == user.id).first()
    if binding is None:
        return BindingOut(bound=False)
    return BindingOut(bound=True, bili_uid=binding.bili_uid)
