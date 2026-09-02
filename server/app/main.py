from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import Base, engine
from .errors import AppError
from . import models  # noqa: F401  # 注册模型到 metadata
from .routers import auth, binding, cards, media, parse, tags


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.dev_mode:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"message": exc.message})


for router in (
    auth.router,
    parse.router,
    cards.router,
    tags.router,
    media.router,
    binding.router,
):
    app.include_router(router)

local_dir = Path(settings.local_storage_dir)
local_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/covers", StaticFiles(directory=str(local_dir)), name="covers")
