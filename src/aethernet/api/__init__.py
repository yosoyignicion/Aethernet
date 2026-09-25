"""API local opcional para que otros scripts consulten la DB."""

from .server import create_app, serve

__all__ = ["create_app", "serve"]
