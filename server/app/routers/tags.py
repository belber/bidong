from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError
from ..models import Tag, User, VideoCard
from ..schemas import CardOut, CardTagsRequest, TagCreate
from ..services.collect import card_to_out
from ..services.tags import get_or_create_tag

router = APIRouter(tags=["tags"])


@router.get("/api/tags", response_model=list[str])
def list_tags(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tags = db.query(Tag).filter(Tag.user_id == user.id).order_by(Tag.name).all()
    return [t.name for t in tags]


@router.post("/api/tags")
def create_tag(
    payload: TagCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tag = get_or_create_tag(db, user.id, payload.name)
    db.commit()
    return {"id": tag.id, "name": tag.name}


@router.post("/api/cards/{card_id}/tags", response_model=CardOut)
def add_card_tags(
    card_id: int,
    payload: CardTagsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = (
        db.query(VideoCard)
        .filter(VideoCard.id == card_id, VideoCard.user_id == user.id)
        .first()
    )
    if card is None:
        raise AppError(404, "卡片不存在")

    existing = {t.name for t in card.tags}
    for name in dict.fromkeys(t.strip() for t in payload.tags if t.strip()):
        if name in existing:
            continue
        tag = get_or_create_tag(db, user.id, name)
        card.tags.append(tag)
        existing.add(name)

    db.commit()
    db.refresh(card)
    return card_to_out(card)

