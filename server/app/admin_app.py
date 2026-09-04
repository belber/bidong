from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
