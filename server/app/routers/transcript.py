from typing import Literal
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError
from ..models import User
from ..schemas import TranscriptOut
from ..services import transcript
from .media import _get_owned_card

router = APIRouter(tags=['transcript'])


@router.post('/api/cards/{card_id}/transcript', response_model=TranscriptOut)
def create(card_id: int, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    card = _get_owned_card(db, user, card_id)
    job = transcript.submit(db, user, card)
    response.status_code = 202 if job.status in transcript.ACTIVE else 200
    return transcript.view(job)


@router.get('/api/cards/{card_id}/transcript', response_model=TranscriptOut)
def get(card_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return transcript.view(transcript.find(db, _get_owned_card(db, user, card_id)))


@router.get('/api/cards/{card_id}/transcript/export')
def export(card_id: int, format: Literal['txt','srt'] = 'txt', user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    card = _get_owned_card(db, user, card_id)
    job = transcript.find(db, card)
    if job is None or job.status != 'completed':
        raise AppError(409, '文案尚未完成，请提取完成后再导出')
    return Response(transcript.export_text(job, format), media_type='text/plain; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{card.bvid}.{format}"'})
