from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import router
from app.core.config import settings
from app.db.session import initialize_database, mark_stale_runs
from app.templating import templates

BASE_DIR = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    interrupted = mark_stale_runs()
    if interrupted:
        LOGGER.warning("Marked %s interrupted parse runs as failed", interrupted)
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        description="Локальный веб-интерфейс для парсинга карточек Ozon.",
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "static")),
        name="static",
    )
    application.include_router(router)

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and not request.url.path.startswith("/api/"):
            return templates.TemplateResponse(
                request,
                "404.html",
                {"request": request},
                status_code=404,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    return application


app = create_app()
