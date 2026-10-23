from fastapi import APIRouter

from app.api import health, pages, runs, search_pages, searches

router = APIRouter()
router.include_router(health.router)
router.include_router(runs.router)
router.include_router(searches.router)
router.include_router(pages.router)
router.include_router(search_pages.router)
