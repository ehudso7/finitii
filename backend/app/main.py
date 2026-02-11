from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.errors import register_error_handlers
from app.core.middleware import RequestIDMiddleware
from app.routers import (
    accounts, auth, bills, cheat_codes, coach, consent, forecast, goals,
    learn, money_graph, onboarding, practice, recurring, transactions, user,
    vault,
)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id"],
)
app.add_middleware(RequestIDMiddleware)

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
