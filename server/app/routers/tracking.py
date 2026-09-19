from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import User, VisitEvent
from ..schemas import VisitEventRequest

router = APIRouter(tags=["tracking"])


@router.post("/api/visit-events")
def report_visit(
    payload: VisitEventRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = VisitEvent(user_id=user.id, path=(payload.path or "")[:128])
    db.add(event)
    db.commit()
    return {"ok": True}
