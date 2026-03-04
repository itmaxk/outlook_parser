import sys
sys.coinit_flags = 0  # STA — must be set before any COM imports

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import HOST, PORT, LOG_LEVEL
from app.db import init_db
from app.api.router import api_router
from app.outlook.watcher import start_watcher, stop_watcher

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized")
    start_watcher()
    yield
    stop_watcher()


app = FastAPI(title="Outlook Parser", lifespan=lifespan)
app.include_router(api_router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL)
