"""FastAPI application factory and shared ASGI application."""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.llm.openrouter_client import OpenRouterClient


def create_app() -> FastAPI:
    """Build the application without requiring provider credentials at import."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        timeout = get_settings().openrouter_timeout_seconds
        application.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        application.state.openrouter_client = OpenRouterClient(
            get_settings(), http_client=application.state.http_client
        )
        try:
            yield
        finally:
            await application.state.http_client.aclose()

    application = FastAPI(title="GridWise LLM", version="0.1.0", lifespan=lifespan)

    @application.exception_handler(RequestValidationError)
    async def invalid_request_handler(request, exc):
        return JSONResponse(status_code=400, content={"detail": "Invalid request"})

    application.include_router(router)
    return application


app = create_app()
