"""Persistent, single-consumer queue. Importing this module never starts ASR."""
import hashlib
import json
import logging
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session
from ..config import settings
from ..errors import AppError
from ..models import TranscriptJob, TranscriptQueue, TranscriptRequest
from ..time import utcnow_naive

ACTIVE = ('queued', 'processing')
LEASE_SECONDS = 120
log = logging.getLogger('bidong.transcript')


def lock_queue(db):
    # Seed via dialect-native upsert, including tests that create tables directly.
    if db.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(insert(TranscriptQueue).values(id=1, revision=0, worker_token='', lease_until=0, heartbeat_at=0).on_conflict_do_nothing(index_elements=['id']))
    db.execute(update(TranscriptQueue).where(TranscriptQueue.id == 1).values(revision=TranscriptQueue.revision+1))
    return db.get(TranscriptQueue, 1, populate_existing=True)


def key_for(card):
    model = settings.transcript_sensevoice_model_path if settings.transcript_engine == 'sensevoice' else settings.transcript_model_path
    value = [card.platform, card.bvid, card.cid, settings.transcript_cache_version,
             settings.transcript_language, settings.transcript_engine, Path(model).name,
             settings.transcript_chunk_seconds, settings.transcript_chunk_context_seconds]
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def find(db, card):
    return db.scalar(select(TranscriptJob).where(TranscriptJob.cache_key == key_for(card)))


def view(job):
    if job is None:
        return {'status': 'idle', 'segments': [], 'source': '', 'language': '', 'error': ''}
    return {'id': job.id, 'status': job.status, 'segments': json.loads(job.segments_json),
            'source': job.source, 'language': job.language, 'error': job.error}


def submit(db, user, card):
    queue = lock_queue(db)
    job = find(db, card)
    if job and job.status in ('completed', 'no_speech'):
        db.commit()
        return job
    # Do not accept tasks without a live worker. Subtitle-only workers are valid.
    if queue.heartbeat_at < int(time.time())-LEASE_SECONDS:
        raise AppError(503, '文案服务暂未就绪，请稍后再试', 'transcript_worker_unavailable')
    own_active = db.scalar(select(func.count()).select_from(TranscriptRequest).join(TranscriptJob).where(
        TranscriptRequest.user_id == user.id, TranscriptJob.status.in_(ACTIVE),
        TranscriptJob.id != (job.id if job else -1)))
    if own_active:
        raise AppError(429, '已有文案正在提取，请完成后再试')
    if not job or job.status == 'failed':
        queued = db.scalar(select(func.count()).select_from(TranscriptJob).where(TranscriptJob.status == 'queued'))
        if queued >= settings.transcript_queue_limit:
            raise AppError(429, '文案任务较多，请稍后再试')
        if job is None:
            data = {k: getattr(card, k) for k in ('platform','bvid','cid','duration','title','source_url')}
            job = TranscriptJob(cache_key=key_for(card), input_json=json.dumps(data, ensure_ascii=False))
            db.add(job)
        else:
            job.status = 'queued'; job.error = ''; job.recoveries = 0
            job.updated_at = utcnow_naive()
        db.flush()
    request = db.scalar(select(TranscriptRequest).where(TranscriptRequest.user_id == user.id, TranscriptRequest.job_id == job.id))
    if request is None:
        db.add(TranscriptRequest(user_id=user.id, job_id=job.id))
    db.commit()
    return job


def platform_subtitles(data):
    if data['platform'] != 'bilibili':
        return []
    from .bilibili import BiliClient
    client = BiliClient()
    try:
        return client.get_transcript_segments(data['bvid'], data['cid'])
    finally:
        client.close()


def recognize(data):
    from .transcript_audio import recognize as run
    return run(data)


def announce(engine):
    with Session(engine) as db:
        lock_queue(db)
        db.execute(update(TranscriptQueue).where(TranscriptQueue.id == 1).values(heartbeat_at=int(time.time())))
        db.commit()


def _heartbeat(engine, token, stop):
    while not stop.wait(10):
        try:
            with Session(engine) as db:
                now = int(time.time())
                result = db.execute(update(TranscriptQueue).where(TranscriptQueue.id == 1, TranscriptQueue.worker_token == token).values(lease_until=now+LEASE_SECONDS, heartbeat_at=now))
                db.commit()
                if not result.rowcount:
                    return
        except Exception:
            log.exception('transcript heartbeat failed')


def work_once(engine):
    token = uuid.uuid4().hex
    with Session(engine, expire_on_commit=False) as db:
        queue = lock_queue(db)
        now = int(time.time())
        queue.heartbeat_at = now
        if queue.worker_token and queue.lease_until > now:
            db.commit(); return False
        # Reclaim one crashed task once; queue serialization prevents two consumers.
        for stale in db.scalars(select(TranscriptJob).where(TranscriptJob.status == 'processing')):
            stale.status = 'queued' if stale.recoveries < 1 else 'failed'
            stale.recoveries += 1
            stale.error = '' if stale.status == 'queued' else '提取进程中断，请重试'
        db.flush()
        job = db.scalar(select(TranscriptJob).where(TranscriptJob.status == 'queued').order_by(TranscriptJob.created_at, TranscriptJob.id).limit(1))
        if job is None:
            queue.worker_token = ''; queue.lease_until = 0
            db.commit(); return False
        queue.worker_token = token; queue.lease_until = now+LEASE_SECONDS
        job.status = 'processing'; job.updated_at = utcnow_naive()
        job_id, data, cache_key = job.id, json.loads(job.input_json), job.cache_key
        db.commit()
    stop = threading.Event()
    heart = threading.Thread(target=_heartbeat, args=(engine, token, stop), daemon=True)
    heart.start()
    status, source, language, segments, error = 'failed', '', '', [], ''
    try:
        if key_for(SimpleNamespace(**data)) != cache_key:
            raise AppError(409, '识别配置已更新，请重新提取文案')
        segments = platform_subtitles(data)
        source = 'platform'
        if not segments:
            if data['duration'] > settings.transcript_max_seconds:
                raise AppError(422, '暂无平台字幕，语音识别仅支持30分钟以内的视频')
            source = 'asr'; language = settings.transcript_language
            segments = recognize(data)
        status = 'completed' if segments else 'no_speech'
    except AppError as exc:
        error = exc.message
    except Exception:
        # Never persist signed media URLs/cookies from upstream exception messages.
        log.exception('transcript job %s failed', job_id)
        error = '文案提取未完成，请稍后重试'
    finally:
        stop.set(); heart.join(timeout=12)
    with Session(engine) as db:
        queue = lock_queue(db)
        if queue.worker_token != token:
            db.rollback(); return True
        job = db.get(TranscriptJob, job_id)
        job.status = status; job.source = source; job.language = language
        job.segments_json = json.dumps(segments, ensure_ascii=False)
        job.error = error; job.updated_at = utcnow_naive()
        queue.worker_token = ''; queue.lease_until = 0; queue.heartbeat_at = int(time.time())
        db.commit()
    log.info('transcript job=%s status=%s source=%s segments=%s', job_id, status, source, len(segments))
    return True


def srt_time(seconds):
    ms = max(0, round(float(seconds)*1000))
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'


def export_text(job, format):
    segments = json.loads(job.segments_json)
    if format == 'txt':
        return '\n'.join(s['text'] for s in segments)
    return '\n\n'.join(f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{s['text']}" for i,s in enumerate(segments,1))+'\n'
