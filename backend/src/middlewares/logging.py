import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Logs method/path/status/duration/request-id only — never the request or response
    body (spec §36 rule 18: never log OTP/PIN/CVV/payment data; a body-dumping log line is
    exactly how that rule gets violated by accident)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        request_id = getattr(request.state, "request_id", None)
        logger.info(
            "%s %s %s %sms request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
