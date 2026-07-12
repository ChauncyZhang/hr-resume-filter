import logging
import re
import secrets
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.app.core.logging import configure_logging
from server.app.core.probes import ReadinessProbe
from server.app.core.settings import Settings


TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
logger = logging.getLogger(__name__)


def _new_trace_id() -> str:
    return secrets.token_hex(16)


def create_app(
    settings: Settings | None = None,
    *,
    database_probe: ReadinessProbe | None = None,
    storage_probe: ReadinessProbe | None = None,
) -> FastAPI:
    settings = settings or Settings.from_environment()

    if database_probe is None or storage_probe is None:
        from server.app.core.storage import ObjectStorageProbe, create_storage_client
        from server.app.db.session import DatabaseProbe, create_engine

        database_probe = database_probe or DatabaseProbe(create_engine(settings.database_url))
        storage_probe = storage_probe or ObjectStorageProbe(
            create_storage_client(
                settings.object_storage_endpoint,
                settings.object_storage_access_key,
                settings.object_storage_secret_key,
                secure=settings.object_storage_secure,
            ),
            settings.object_storage_bucket,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        yield

    app = FastAPI(title="UX-09 Recruiting API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def trace_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
        supplied = request.headers.get("x-trace-id", "")
        trace_id = supplied if TRACE_ID_PATTERN.fullmatch(supplied) else _new_trace_id()
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        logger.info(
            "request_complete",
            extra={
                "context": {
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                }
            },
        )
        return response

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready(request: Request):  # type: ignore[no-untyped-def]
        try:
            await database_probe.check()
            await storage_probe.check()
        except Exception as error:
            logger.warning(
                "dependency_readiness_failed",
                extra={
                    "context": {
                        "trace_id": request.state.trace_id,
                        "error_type": type(error).__name__,
                    }
                },
            )
            return JSONResponse(
                status_code=503,
                media_type="application/problem+json",
                content={
                    "type": "about:blank",
                    "title": "Service unavailable",
                    "status": 503,
                    "detail": "Required dependencies are unavailable.",
                    "code": "dependencies_unavailable",
                    "trace_id": request.state.trace_id,
                    "errors": [],
                },
            )
        return {"status": "ready"}

    return app
