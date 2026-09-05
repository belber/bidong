from pathlib import Path
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  # 注册模型
from .admin import router
from .config import settings
from .db import Base, engine
from .services import config_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.dev_mode:
        Base.metadata.create_all(bind=engine)
    # 让 admin_config 始终有与运行时一致的有效值（缺失才写，不覆盖用户已保存值）
    from .db import SessionLocal

    db = SessionLocal()
    try:
        config_store.seed_defaults(db)
    except Exception:  # noqa: BLE001  # 表未迁移时不阻塞启动
        pass
    finally:
        db.close()
    yield


app = FastAPI(title=f"{settings.app_name} admin", lifespan=lifespan)

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


@app.middleware("http")
async def log_admin_requests(request: Request, call_next):
    path = request.url.path
    start = time.monotonic()
    qs = str(request.query_params) if request.query_params else ""
    body = b""
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()
        async def receive():
            return {"type": "http.request", "body": body}
        request._receive = receive
    body_str = body.decode("utf-8", errors="replace")[:1000] if body else ""
    if qs:
        logger.info(">>> [admin] %s %s?%s body=%s", request.method, path, qs, body_str)
    else:
        logger.info(">>> [admin] %s %s body=%s", request.method, path, body_str)
    response = await call_next(request)
    resp_body = b""
    async for chunk in response.body_iterator:
        resp_body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
    resp_str = resp_body.decode("utf-8", errors="replace")[:1000]
    duration = int((time.monotonic() - start) * 1000)
    logger.info("<<< [admin] %s %s %d (%dms) resp=%s", request.method, path, response.status_code, duration, resp_str)
    from starlette.responses import Response as StarletteResponse
    return StarletteResponse(
        content=resp_body, status_code=response.status_code,
        headers=dict(response.headers), media_type=response.media_type,
    )


@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(router)

admin_static = Path(__file__).parent / "admin_static"
admin_static.mkdir(parents=True, exist_ok=True)
app.mount("/admin", StaticFiles(directory=str(admin_static), html=True), name="admin")


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/admin/")
