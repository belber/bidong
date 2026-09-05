from contextlib import asynccontextmanager
import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import Base, engine
from .errors import AppError
from . import models  # noqa: F401  # 注册模型到 metadata
from .routers import auth, binding, cards, help, media, meta, parse, tags


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.dev_mode:
        Base.metadata.create_all(bind=engine)
    yield


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
    return JSONResponse(status_code=exc.status_code, content={"message": exc.message})


for router in (
    auth.router,
    parse.router,
    cards.router,
    tags.router,
    media.router,
    binding.router,
    help.router,
    meta.router,
):
    app.include_router(router)

local_dir = Path(settings.local_storage_dir)
local_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/covers", StaticFiles(directory=str(local_dir)), name="covers")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    start = time.monotonic()
    # 入参
    qs = str(request.query_params) if request.query_params else ""
    body = b""
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()
        async def receive():
            return {"type": "http.request", "body": body}
        request._receive = receive
    body_str = body.decode("utf-8", errors="replace")[:1000] if body else ""
    if qs:
        logger.info(">>> %s %s?%s body=%s", request.method, path, qs, body_str)
    else:
        logger.info(">>> %s %s body=%s", request.method, path, body_str)
    # 执行
    response = await call_next(request)
    # 出参
    resp_body = b""
    async for chunk in response.body_iterator:
        resp_body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
    resp_str = resp_body.decode("utf-8", errors="replace")[:1000]
    duration = int((time.monotonic() - start) * 1000)
    logger.info("<<< %s %s %d (%dms) resp=%s", request.method, path, response.status_code, duration, resp_str)
    from starlette.responses import Response as StarletteResponse
    return StarletteResponse(
        content=resp_body, status_code=response.status_code,
        headers=dict(response.headers), media_type=response.media_type,
    )
