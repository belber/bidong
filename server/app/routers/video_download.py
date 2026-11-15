import time
from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import get_current_user
from ..models import User, VideoDownloadJob
from ..errors import AppError
from ..services import video_download as service
from .media import _get_owned_card

router = APIRouter(tags=['video-download'])

class Request(BaseModel):
    qn: int | None = Field(default=None, gt=0)

@router.post('/api/cards/{card_id}/video-download')
def create(card_id: int, body: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = service.submit(db, user, _get_owned_card(db, user, card_id), body.qn)
    response.status_code = 202 if result['status'] in service.ACTIVE else 200
    return result

@router.get('/api/cards/{card_id}/video-download')
def get(card_id: int, qn: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.require_enabled(db)
    return service.view(db, service.find(db, user, _get_owned_card(db, user, card_id), qn))

@router.get('/api/cards/{card_id}/video-download/file')
def file(card_id: int, job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.require_enabled(db); _get_owned_card(db, user, card_id)
    service.lock(db)
    job = db.get(VideoDownloadJob, job_id)
    if not job or job.user_id != user.id or job.card_id != card_id:
        raise AppError(404, '文件不存在')
    if service.view_locked(job) != 'ready':
        db.commit(); raise AppError(410, '文件已过期，请重新准备')
    job.serve_until = int(time.time()) + 900
    job.expires_at = max(job.expires_at, job.serve_until)
    path = service.path_for(job); db.commit()
    return FileResponse(path, media_type='video/mp4', filename=f'video-{card_id}.mp4')
