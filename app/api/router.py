from fastapi import APIRouter

from app.api import health, pages, runs

router = APIRouter()
router.include_router(health.router)
router.include_router(runs.router)
router.include_router(pages.router)
