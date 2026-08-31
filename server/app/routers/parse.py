from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import ParseRequest, ParseResult, SubtitleLine
from ..services.collect import card_to_out, collect_video

router = APIRouter(tags=["parse"])


@router.post("/api/parse", response_model=ParseResult)
def parse(
    payload: ParseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card, subtitles = collect_video(db, user, payload.url)
    out = card_to_out(card)
    lines = [SubtitleLine(t=s["t"], text=s["text"]) for s in subtitles[:500]]
    return ParseResult(**out.model_dump(), subtitles=lines)
