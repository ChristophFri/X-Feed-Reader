"""FastAPI application factory — entry point for the web app."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.config import get_settings
from web.routers import api, auth, dashboard, pages, webhooks

WEB_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Auto-create tables for SQLite (dev mode); PostgreSQL uses Alembic
    from web.db.session import engine
    from web.models import Base

    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Initialize third-party API keys once at startup
    if settings.stripe_secret_key:
        from web.services.subscription_service import init_stripe
        init_stripe()
    if settings.resend_api_key:
        import resend
        resend.api_key = settings.resend_api_key

    # Initialize shared httpx client for connection pooling
    from web.http_client import init_http_client, close_http_client
    await init_http_client()

    yield

    await close_http_client()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    # --- Templates ---
    templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    app.state.templates = templates
    app.state.settings = settings

    # --- Static files ---
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    # --- Error handlers ---
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "status_code": 404,
                "title": "Page not found",
                "message": "The page you're looking for doesn't exist or has been moved.",
            },
            status_code=404,
        )

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc):
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "status_code": 500,
                "title": "Something went wrong",
                "message": "An unexpected error occurred. Please try again later.",
            },
            status_code=500,
        )

    # --- Routers ---
    app.include_router(pages.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(api.router)
    app.include_router(webhooks.router)

    return app


app = create_app()
