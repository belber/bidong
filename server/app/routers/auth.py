from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import LoginRequest, LoginResponse, UserOut
from ..security import create_access_token
from ..services.wechat import resolve_openid
from ..time import utcnow_naive

router = APIRouter(tags=["auth"])


@router.post("/api/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    openid = resolve_openid(payload.code)
    user = db.query(User).filter(User.openid == openid).first()
    if user is None:
        user = User(openid=openid, created_at=utcnow_naive())
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user.id)
    return LoginResponse(access_token=token, user=UserOut(id=user.id, nickname=user.nickname))

