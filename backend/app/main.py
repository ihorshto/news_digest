import logging

from fastapi import FastAPI

from app.api import account, auth
from app.api.csrf import CSRFMiddleware
from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    settings.log_fake_modes()

    app = FastAPI(title="NewsDigest API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(CSRFMiddleware)
    app.include_router(account.router)
    app.include_router(auth.router)
    return app


app = create_app()
