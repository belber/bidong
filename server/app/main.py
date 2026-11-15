import asyncio
from contextlib import asynccontextmanager
import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import Base, SessionLocal, engine
from .schema_check import check_schema
from .errors import AppError
from . import models  # noqa: F401  # 注册模型到 metadata
from .services import crawler as crawler_service
from .routers import (
    auth,
    binding,
    cards,
    help,
    media,
    meta,
    parse,
    public,
    sources,
    tags,
    tracking,
    transcript,
    video_download,
)
from .services import daily_report
from .services import wechat_search


async def _daily_report_loop() -> None:
    while True:
        try:
            db = SessionLocal()
            try:
                daily_report.maybe_send_daily_report(db)
                # 搜一搜数据推送：每天一次增量（开关在管理端）
                wechat_search.maybe_push_search(db)
            finally:
                db.close()
        except Exception:
            logging.getLogger("bidong").exception("daily report failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.dev_mode:
        # 只检查不建表：create_all 会建表但不盖迁移章，反而让库悄悄漂移
        check_schema(engine)
    task = asyncio.create_task(_daily_report_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)

logger = logging.getLogger("bidong")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.warning("API error %s %s -> %d: %s", request.method, request.url.path, exc.status_code, exc.message)
    content: dict = {"message": exc.message}
    if exc.error_type:
        content["error_type"] = exc.error_type
    return JSONResponse(status_code=exc.status_code, content=content)


for router in (
    auth.router,
    parse.router,
    cards.router,
    tags.router,
    media.router,
    binding.router,
    help.router,
    meta.router,
    tracking.router,
    sources.router,
    public.router,
    transcript.router,
    video_download.router,
):
    app.include_router(router)

local_dir = Path(settings.local_storage_dir)
local_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/covers", StaticFiles(directory=str(local_dir)), name="covers")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # 微信搜索爬虫的访问单独记一笔，用于诊断"页面为什么没被收录"
    try:
        if crawler_service.looks_like_crawler(request.headers):
            db = SessionLocal()
            try:
                crawler_service.record_from_headers(
                    db, request.headers, request.url.path, str(request.url.query or "")
                )
            finally:
                db.close()
    except Exception:  # noqa: BLE001  记录失败不能影响正常请求
        logging.getLogger("bidong").exception("crawler visit record failed")

    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    start = time.monotonic()
    # Preserve streaming responses: never accumulate an MP4 (or log signed URLs/tokens).
    response = await call_next(request)
    duration = int((time.monotonic() - start) * 1000)
    logger.info("%s %s -> %d (%dms)", request.method, path, response.status_code, duration)
    return response
