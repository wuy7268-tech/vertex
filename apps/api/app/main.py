import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.runtime import SessionLocal, engine, scheduler, settings
from app.routes import router
from app.seed import seed_workspace

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("vertex")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(engine)
    if settings.vertex_auto_seed:
        db = SessionLocal()
        try:
            if seed_workspace(db):
                log.info("seeded the Vertex workspace")
        finally:
            db.close()
    if settings.vertex_scheduler:
        scheduler.start()
        log.info("scheduler started")
    yield
    scheduler.stop()


app = FastAPI(title="Vertex", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")
