"""Durable video preparation queue, separate from speech recognition."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
import httpx
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session
from ..config import settings
from ..errors import AppError
from ..models import VideoDownloadJob as Job, VideoDownloadQueue as Queue
from . import config_store, media_download

ACTIVE = ('queued', 'processing')
LEASE = 120


def lock(db):
    if db.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(insert(Queue).values(id=1, revision=0, worker_token='', lease_until=0, heartbeat_at=0).on_conflict_do_nothing(index_elements=['id']))
    db.execute(update(Queue).where(Queue.id == 1).values(revision=Queue.revision + 1))
    return db.get(Queue, 1, populate_existing=True)


def announce(engine):
    with Session(engine) as db:
        q = lock(db); q.heartbeat_at = int(time.time()); db.commit()


def plans_from_data(dash, complete, duration):
    plans = {}
    audio = dash.get('audio') or []
    aac = [a for a in audio if str(a.get('codecs', '')).startswith('mp4a') or (not a.get('codecs') and a.get('qn') in (30216, 30232, 30280))]
    chosen = max(aac, key=lambda a: a.get('bandwidth', 0) or a.get('qn', 0), default=None)
    def size(s):
        return int(s.get('size') or (s.get('bandwidth', 0) or 0) * (duration or 0) / 8)
    for v in dash.get('video') or []:
        if not (str(v.get('codecs', '')).startswith(('avc1', 'avc3')) or v.get('codecid') == 7):
            continue
        if audio and chosen is None:
            continue
        qn = v['qn']
        plans.setdefault(qn, dict(qn=qn, label=v.get('label') or str(qn), mode='mux', video=v, audio=chosen,
                                  has_audio=bool(chosen), estimated_size=size(v) + (size(chosen) if chosen else 0)))
    for v in complete.get('durl') or []:
        fmt = v.get('format') or ''
        if v.get('complete') and (fmt.startswith('mp4') or (not fmt and '.mp4' in v.get('url', '').split('?')[0])):
            plans[v['qn']] = dict(qn=v['qn'], label=v.get('label') or str(v['qn']), mode='direct', stream=v,
                                  has_audio=(bool(dash.get('audio')) if dash.get('video') else None), estimated_size=size(v))
    return sorted(plans.values(), key=lambda p: p['qn'], reverse=True)


def resolve_plans(card, qn=None):
    from .bilibili import BiliClient
    client = BiliClient()
    dash = {}; complete = {}; errors = []
    try:
        try:
            dash = client.get_playurl(card.bvid, card.cid, fnval=16, qn=qn)
        except AppError as exc:
            errors.append(exc)
        try:
            complete = client.get_playurl(card.bvid, card.cid, fnval=1, platform='html5', qn=qn)
        except AppError as exc:
            errors.append(exc)
    finally:
        client.close()
    if len(errors) == 2:
        raise errors[0]
    plans = plans_from_data(dash, complete, card.duration)
    return [p for p in plans if qn is None or p['qn'] == qn]


def require_enabled(db):
    if not config_store.media_switches(db)['clean']:
        raise AppError(403, '该下载未开放')


def path_for(job):
    return Path(settings.video_download_cache_dir) / f'{int(job.id)}.mp4'


def find(db, user, card, qn=None):
    query = select(Job).where(Job.user_id == user.id, Job.card_id == card.id)
    if qn is not None:
        query = query.where(Job.qn == qn)
    return db.scalar(query.order_by(Job.id.desc()).limit(1))


def view(db, job):
    if job is None:
        return {'status': 'idle'}
    if job.status == 'ready':
        lock(db)
        db.refresh(job)
        view_locked(job)
        db.commit()
    return dict(id=job.id, status=job.status, mode='file', qn=job.qn, has_audio=job.has_audio,
                estimated_size=job.estimated_size, size_bytes=job.size_bytes, error=job.error,
                file_url=f'/api/cards/{job.card_id}/video-download/file?job_id={job.id}' if job.status == 'ready' else '')


def submit(db, user, card, qn=None):
    require_enabled(db)
    previous = find(db, user, card, qn)
    if previous and view(db, previous)['status'] in (*ACTIVE, 'ready'):
        return view(db, previous)
    plans = resolve_plans(card, qn)
    if not plans:
        raise AppError(422, '该清晰度暂不支持完整视频下载')
    plan = plans[0]
    if plan['mode'] == 'direct':
        return dict(status='ready', mode='direct', qn=plan['qn'], has_audio=plan['has_audio'],
                    estimated_size=plan['estimated_size'], candidates=media_download.build_candidates(db, [plan['stream']], kind='video'))
    if plan['estimated_size'] > settings.video_download_max_input_bytes:
        raise AppError(413, '需合并的视频超过 512MiB 限制，请选择其他清晰度')
    queue = lock(db)
    # Repeat under the queue lock to make concurrent submissions idempotent.
    job = find(db, user, card, plan['qn'])
    if job and view_locked(job) in (*ACTIVE, 'ready'):
        db.commit(); return view(db, job)
    identity = {k: getattr(card, k) for k in ('platform', 'bvid', 'cid', 'duration')}
    key = hashlib.sha256(json.dumps([user.id, identity['platform'], identity['bvid'], identity['cid'], plan['qn']], sort_keys=True).encode()).hexdigest()
    if job is None:
        job = db.scalar(select(Job).where(Job.cache_key == key))
        if job is not None:
            job.card_id = card.id
            if view_locked(job) in (*ACTIVE, 'ready'):
                db.commit(); return view(db, job)
    if queue.heartbeat_at < time.time() - LEASE:
        raise AppError(503, '视频准备服务暂未就绪，请稍后再试')
    if db.scalar(select(func.count()).select_from(Job).where(Job.user_id == user.id, Job.status.in_(ACTIVE))):
        raise AppError(429, '已有视频正在准备，请完成后再试')
    if db.scalar(select(func.count()).select_from(Job).where(Job.status == 'queued')) >= settings.video_download_queue_limit:
        raise AppError(429, '视频等待队列已满，请稍后再试')
    if job is None:
        job = Job(cache_key=key, user_id=user.id, card_id=card.id, qn=plan['qn'], input_json=json.dumps(identity))
        db.add(job)
    job.status = 'queued'; job.error = ''; job.has_audio = plan['has_audio']
    job.estimated_size = plan['estimated_size']; job.size_bytes = 0; job.expires_at = 0; job.serve_until = 0; job.recoveries = 0
    db.commit()
    return view(db, job)


def view_locked(job):
    if job.status == 'ready' and (job.expires_at <= time.time() or not path_for(job).is_file()):
        job.status = 'expired'
    return job.status


def cleanup(db, reserve=0):
    root = Path(settings.video_download_cache_dir); root.mkdir(parents=True, exist_ok=True)
    now = time.time()
    ready = list(db.scalars(select(Job).where(Job.status == 'ready').order_by(Job.expires_at)))
    for job in ready:
        if job.serve_until <= now and (job.expires_at <= now or not path_for(job).is_file()):
            path_for(job).unlink(missing_ok=True); job.status = 'expired'
    valid = {f'{j.id}.mp4' for j in ready if j.status == 'ready'}
    for p in root.glob('*.mp4'):
        if p.name not in valid:
            p.unlink(missing_ok=True)
    used = sum(p.stat().st_size for p in root.glob('*.mp4'))
    for job in ready:
        if used + reserve <= settings.video_download_cache_max_bytes:
            break
        if job.status == 'ready' and job.serve_until <= now:
            p = path_for(job); n = p.stat().st_size if p.exists() else 0
            p.unlink(missing_ok=True); job.status = 'expired'; used -= n
    if used + reserve > settings.video_download_cache_max_bytes:
        raise AppError(507, '视频缓存空间不足，请稍后再试')
    if shutil.disk_usage(root).free < reserve * 2 + 64 * 1024 * 1024:
        raise AppError(507, '服务器磁盘空间不足，请稍后再试')
    tmp = root / '.tmp'
    if tmp.exists():
        for p in tmp.iterdir():
            if p.is_dir() and p.stat().st_mtime < now - settings.video_download_timeout_seconds - LEASE:
                shutil.rmtree(p, ignore_errors=True)


def claim(engine, token):
    with Session(engine) as db:
        queue = lock(db); now = int(time.time()); queue.heartbeat_at = now
        if queue.worker_token and queue.lease_until > now:
            db.commit(); return None
        for old in db.scalars(select(Job).where(Job.status == 'processing')):
            old.status = 'queued' if old.recoveries < 1 else 'failed'
            old.error = '' if old.recoveries < 1 else '视频准备中断，请重试'
            old.recoveries += 1
        cleanup(db)
        job = db.scalar(select(Job).where(Job.status == 'queued').order_by(Job.id).limit(1))
        if job:
            job.status = 'processing'; queue.worker_token = token; queue.lease_until = now + LEASE
        db.commit()
        return job.id if job else None


def heartbeat(engine, token):
    with Session(engine) as db:
        q = lock(db)
        if q.worker_token != token:
            raise RuntimeError('video worker lease lost')
        q.heartbeat_at = int(time.time()); q.lease_until = int(time.time()) + LEASE; db.commit()


def fetch_stream(stream, target, deadline, budget):
    from .transcript_audio import public_url
    from .bilibili import UA
    urls = [stream.get('url')] + list(stream.get('backup_urls') or [])
    for url in urls:
        if not url:
            continue
        try:
            with httpx.Client(follow_redirects=False, timeout=20, headers={'Referer': 'https://www.bilibili.com/', 'User-Agent': UA}) as client:
                for _ in range(6):
                    if time.monotonic() >= deadline:
                        raise TimeoutError()
                    public_url(url)
                    with client.stream('GET', url) as response:
                        if response.is_redirect:
                            url = str(response.url.join(response.headers['location'])); continue
                        response.raise_for_status()
                        if int(response.headers.get('content-length') or 0) > budget:
                            raise AppError(413, '需合并的视频超过大小限制')
                        size = 0
                        with open(target, 'wb') as file:
                            for chunk in response.iter_bytes(256 * 1024):
                                if time.monotonic() >= deadline:
                                    raise TimeoutError()
                                size += len(chunk)
                                if size > budget:
                                    raise AppError(413, '需合并的视频超过大小限制')
                                file.write(chunk)
                        if not size:
                            raise ValueError('empty media')
                        return size
                raise ValueError('too many redirects')
        except (AppError, TimeoutError):
            raise
        except Exception:
            target.unlink(missing_ok=True)
    raise AppError(502, '音视频文件获取失败，请稍后重试')


def ffmpeg(args, deadline):
    binary = settings.video_download_ffmpeg_bin or settings.transcript_ffmpeg_bin or 'ffmpeg'
    # communicate drains stderr; kill the entire process group on timeout or worker shutdown.
    import signal
    proc = subprocess.Popen([binary, '-nostdin', '-hide_banner', *args], stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, start_new_session=True)
    try:
        _, stderr = proc.communicate(timeout=max(.1, deadline - time.monotonic()))
    except BaseException:
        os.killpg(proc.pid, signal.SIGKILL); proc.communicate(); raise
    return proc.returncode, stderr.decode('utf-8', errors='replace')


def validate(path, has_audio, deadline):
    code, text = ffmpeg(['-i', str(path), '-map', '0:v:0', *(['-map', '0:a:0'] if has_audio else []), '-c', 'copy', '-f', 'null', '-'], deadline)
    import re
    if code or not re.search(r'Video: h264\b', text) or (has_audio and not re.search(r'Audio: aac\b', text)):
        raise AppError(422, '该清晰度暂不支持完整视频下载')
    if not has_audio and re.search(r'Audio:', text):
        raise AppError(422, '音轨信息不一致，请重试')


def prepare(engine, job_id, token):
    deadline = time.monotonic() + settings.video_download_timeout_seconds
    root = Path(settings.video_download_cache_dir)
    try:
        with Session(engine) as db:
            job = db.get(Job, job_id); identity = json.loads(job.input_json); qn = job.qn
            q = lock(db)
            if q.worker_token != token:
                raise RuntimeError('lease lost')
            cleanup(db, settings.video_download_max_input_bytes)
            db.commit()
        plans = resolve_plans(SimpleNamespace(**identity), qn)
        if not plans:
            raise AppError(422, '该清晰度暂不支持完整视频下载')
        plan = plans[0]
        (root / '.tmp').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f'job-{job_id}-', dir=root / '.tmp') as work:
            work = Path(work); video = work / 'video'; audio = work / 'audio'; output = work / 'out.mp4'
            limit = settings.video_download_max_input_bytes
            if plan['mode'] == 'direct':
                fetch_stream(plan['stream'], video, deadline, limit)
                _, probe = ffmpeg(['-i', str(video)], deadline)
                has_audio = 'Audio:' in probe
                validate(video, has_audio, deadline)
                shutil.copyfile(video, output)
            else:
                n = fetch_stream(plan['video'], video, deadline, limit)
                has_audio = plan['has_audio']
                args = ['-y', '-i', str(video)]
                if has_audio:
                    fetch_stream(plan['audio'], audio, deadline, limit - n)
                    args += ['-i', str(audio)]
                else:
                    validate(video, False, deadline)
                args += ['-map', '0:v:0'] + (['-map', '1:a:0'] if has_audio else [])
                code, _ = ffmpeg(args + ['-c', 'copy', '-threads', '1', '-movflags', '+faststart', str(output)], deadline)
                if code:
                    raise AppError(422, '视频与音轨合并失败，请重试')
                validate(output, has_audio, deadline)
            if time.monotonic() > deadline:
                raise TimeoutError()
            size = output.stat().st_size
            with Session(engine) as db:
                q = lock(db); job = db.get(Job, job_id)
                if q.worker_token != token or q.lease_until < time.time() or job.status != 'processing':
                    raise RuntimeError('lease lost')
                cleanup(db, size)
                os.replace(output, path_for(job))
                job.status = 'ready'; job.has_audio = has_audio; job.size_bytes = size
                job.expires_at = int(time.time()) + settings.video_download_cache_seconds
                q.worker_token = ''; q.lease_until = 0; db.commit()
    except Exception as exc:
        with Session(engine) as db:
            q = lock(db); job = db.get(Job, job_id)
            if q.worker_token == token and job.status == 'processing':
                job.status = 'failed'
                job.error = exc.message if isinstance(exc, AppError) else ('视频准备超时，请重试' if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)) else '视频准备失败，请重试')
                q.worker_token = ''; q.lease_until = 0; db.commit()
