"""Run with python -m app.transcript_worker. One process, no idle ASR model."""
import logging
from pathlib import Path
import shutil
import signal
import time
from .config import settings
from .db import engine
from .schema_check import check_schema
from .services.transcript import work_once, announce


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    check_schema(engine)
    # Only remove old temp dirs; another worker may still own a live task.
    root = Path(settings.transcript_temp_dir)
    root.mkdir(parents=True, exist_ok=True)
    for path in root.glob('job-*'):
        if path.is_dir() and time.time()-path.stat().st_mtime > settings.transcript_timeout_seconds+300:
            shutil.rmtree(path, ignore_errors=True)
    def shutdown(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    announce(engine)
    while True:
        try:
            if not work_once(engine): time.sleep(3)
        except Exception:
            logging.exception('transcript worker iteration failed')
            time.sleep(3)


if __name__ == '__main__':
    main()
