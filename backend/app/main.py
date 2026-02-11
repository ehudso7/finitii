import logging
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.core.errors import register_error_handlers
from app.core.middleware import RequestIDMiddleware, AccessLogMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.routers import (
    accounts, auth, bills, cheat_codes, coach, consent, forecast, goals,
    learn, money_graph, onboarding, practice, recurring, transactions, user,
    vault,
)

# Validate session secret in production
if settings.is_production and settings.secret_key == "change-me-in-production":
    raise RuntimeError(
        "SECRET_KEY must be set to a secure random value in production. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

if not settings.is_production and settings.secret_key == "change-me-in-production":
    warnings.warn("SECRET_KEY is using default value. Set it for production.", stacklevel=1)

logger = logging.getLogger("finitii")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create database tables on startup if they don't exist."""
    from app.models.base import Base
    # Import all models so Base.metadata is populated
    from app.models import (  # noqa: F401
        user, consent as consent_model, audit, session, account, merchant,
        category, transaction, recurring, onboarding, goal, cheat_code,
        forecast, coach_memory, learn, practice, vault as vault_model,
    )
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    logger.info("Database tables verified/created")
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Middleware — order matters (last added = outermost = first to execute)
# Correct order: CORS outermost so all responses get CORS headers (including 429s)
cors_kwargs = {
    "allow_origins": settings.cors_origins_list,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "expose_headers": ["x-request-id"],
}
if settings.cors_allow_origin_regex:
    cors_kwargs["allow_origin_regex"] = settings.cors_allow_origin_regex
app.add_middleware(RequestIDMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CORSMiddleware, **cors_kwargs)

# Error handlers
register_error_handlers(app)

# Routers
app.include_router(auth.router)
app.include_router(consent.router)
app.include_router(user.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(recurring.router)
app.include_router(money_graph.router)
app.include_router(onboarding.router)
app.include_router(goals.router)
app.include_router(cheat_codes.router)
app.include_router(coach.router)
app.include_router(forecast.router)
app.include_router(bills.router)
app.include_router(learn.router)
app.include_router(practice.router)
app.include_router(vault.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name, "version": "0.1.0"}
