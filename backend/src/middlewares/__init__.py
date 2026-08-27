from fastapi import FastAPI

from src.config import settings
from src.middlewares.cors import add_cors_middleware
from src.middlewares.logging import AccessLogMiddleware
from src.middlewares.request_context import RequestContextMiddleware


def register_middlewares(app: FastAPI) -> None:
    # add_middleware() stacks LIFO: the LAST one added runs FIRST on the way in, and LAST
    # on the way out — so RequestContextMiddleware must be added last to wrap everything
    # else (every other middleware's logging can then see request.state.request_id).
    add_cors_middleware(app, origins=settings.CORS_ORIGINS)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestContextMiddleware)
