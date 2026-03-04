from fastapi import APIRouter

from app.api.rules import router as rules_router
from app.api.logs import router as logs_router

api_router = APIRouter()
api_router.include_router(rules_router)
api_router.include_router(logs_router)
