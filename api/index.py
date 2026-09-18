"""Vercel ASGI entrypoint; all behavior remains in the shared application."""

from app.main import app

__all__ = ["app"]
