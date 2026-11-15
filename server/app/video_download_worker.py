"""Independent single-video worker with a hard task deadline, no ASR or Redis."""
import logging
import multiprocessing
import shutil
import signal
import time
import uuid
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from .config import settings
from .db import engine
from .models import VideoDownloadJob
from .schema_check import check_schema
from .services import video_download as service


def _prepare(database_url, job_id, token):
    # A subprocess also bounds platform/DNS calls that cannot honor a Python timer.
    def timeout(*_):
        raise TimeoutError()
    signal.signal(signal.SIGTERM, timeout)
    local_engine = create_engine(database_url)
    try:
        service.prepare(local_engine, job_id, token)
    finally:
        local_engine.dispose()


def work_once(engine):
    token = uuid.uuid4().hex
    job_id = service.claim(engine, token)
    if job_id is None:
        return False
    child = multiprocessing.get_context('spawn').Process(target=_prepare,
        args=(engine.url.render_as_string(hide_password=False), job_id, token))
    child.start()
    started = time.monotonic(); next_pulse = started + 10
    timed_out = False
    try:
        while child.is_alive():
            child.join(timeout=1)
            now = time.monotonic()
            if now - started >= settings.video_download_timeout_seconds:
                timed_out = True; break
            if now >= next_pulse:
                service.heartbeat(engine, token); next_pulse = now + 10
    finally:
        if child.is_alive():
            child.terminate(); child.join(timeout=5)
        if child.is_alive():
            child.kill(); child.join(timeout=5)
        with Session(engine) as db:
            queue = service.lock(db); job = db.get(VideoDownloadJob, job_id)
            if queue.worker_token == token and job.status == 'processing':
                job.status = 'failed'
                job.error = '视频准备超时，请重试' if timed_out else '视频准备中断，请重试'
                queue.worker_token = ''; queue.lease_until = 0
                db.commit()
        for path in (Path(settings.video_download_cache_dir) / '.tmp').glob(f'job-{job_id}-*'):
            shutil.rmtree(path, ignore_errors=True)
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    check_schema(engine)
    def shutdown(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown); signal.signal(signal.SIGINT, shutdown)
    while True:
        try:
            if not work_once(engine):
                time.sleep(3)
        except Exception:
            logging.exception('video worker iteration failed')
            time.sleep(3)

if __name__ == '__main__':
    main()
