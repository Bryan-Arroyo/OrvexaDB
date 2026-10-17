import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.admin_users import router as admin_users_router
from app.api.catalog import router as catalog_router
from app.api.inventory import router as inventory_router
from app.api.dashboard import router as dashboard_router
from app.api.purchases import router as purchases_router

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
app = FastAPI(title="OrvexaDB API", docs_url=None, redoc_url=None)
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_users_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(purchases_router, prefix="/api/v1")


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    supplied = request.headers.get("x-correlation-id", "")
    try:
        correlation = str(uuid.UUID(supplied))
    except (ValueError, AttributeError):
        correlation = str(uuid.uuid4())
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request exception correlation_id=%s", correlation)
        response = JSONResponse(status_code=500, content={"detail": "internal server error"})
    response.headers["x-correlation-id"] = correlation
    return response
