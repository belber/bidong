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
from .routers.admin_douyin import router as douyin_router
from .config import settings
from .db import Base, engine
from .schema_check import check_schema
from .services import config_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.dev_mode:
        # 只检查不建表：create_all 会建表但不盖迁移章，反而让库悄悄漂移
        check_schema(engine)
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
    # 管理端请求/响应含 Cookie、密码及 token；日志只记录路由、状态和耗时。
    path = request.url.path
    start = time.monotonic()
    logger.info(">>> [admin] %s %s", request.method, path)
    response = await call_next(request)
    duration = int((time.monotonic() - start) * 1000)
    logger.info("<<< [admin] %s %s %d (%dms)", request.method, path, response.status_code, duration)
    return response


@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(router)
app.include_router(douyin_router)

admin_static = Path(__file__).parent / "admin_static"
admin_static.mkdir(parents=True, exist_ok=True)
app.mount("/admin", StaticFiles(directory=str(admin_static), html=True), name="admin")


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/admin/")
