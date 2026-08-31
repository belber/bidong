from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError
from ..models import Tag, User, VideoCard
from ..schemas import CardOut
from ..services.collect import card_to_out

router = APIRouter(tags=["cards"])


@router.get("/api/cards", response_model=list[CardOut])
def list_cards(
    month: str | None = None,
    tag: str | None = None,
    source: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(VideoCard).filter(VideoCard.user_id == user.id)
    if month:
        q = q.filter(VideoCard.month == month)
    if source:
        q = q.filter(VideoCard.source == source)
    if tag:
        q = q.join(VideoCard.tags).filter(Tag.name == tag)
    q = q.order_by(VideoCard.collected_at.desc())
    return [card_to_out(c) for c in q.all()]


@router.get("/api/cards/{card_id}", response_model=CardOut)
def get_card(
    card_id: int,
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
    return card_to_out(card)


@router.delete("/api/cards/{card_id}", status_code=204)
def delete_card(
    card_id: int,
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
    db.delete(card)
    db.commit()
    return Response(status_code=204)

