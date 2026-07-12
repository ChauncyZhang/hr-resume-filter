import asyncio
import logging
import re
import secrets
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.app.core.logging import configure_logging
from server.app.core.probes import ReadinessProbe, check_readiness
from server.app.core.settings import Settings
from server.app.identity.api import allowed_origin, problem, router as identity_router, session_token
from server.app.identity.service import Clock, IdentityService, TokenSource
from server.app.identity.store import IdentityStore


TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
logger = logging.getLogger(__name__)


def _new_trace_id() -> str:
    return secrets.token_hex(16)


def create_app(
    settings: Settings | None = None,
    *,
    database_probe: ReadinessProbe | None = None,
    storage_probe: ReadinessProbe | None = None,
    clock: Clock | None = None,
    token_source: TokenSource | None = None,
    initialize_identity_schema: bool = False,
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
                connect_timeout_seconds=settings.object_storage_connect_timeout_seconds,
                read_timeout_seconds=settings.object_storage_read_timeout_seconds,
                total_timeout_seconds=settings.object_storage_total_timeout_seconds,
            ),
            settings.object_storage_bucket,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        if initialize_identity_schema:
            app.state.identity_store.create_schema()
        yield

    app = FastAPI(title="UX-09 Recruiting API", lifespan=lifespan)
    app.state.settings = settings
    app.state.identity_store = IdentityStore(settings.database_url)
    app.state.identity_service = IdentityService(
        app.state.identity_store, clock or Clock(), token_source or TokenSource()
    )
    app.include_router(identity_router)
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
        response = None
        if request.url.path.startswith("/api/v1") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            service: IdentityService = request.app.state.identity_service
            network = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
            if not allowed_origin(request):
                event = "authentication.logout" if request.url.path == "/api/v1/auth/logout" else "csrf.denied"
                service.audit_denial(event, token=session_token(request), trace_id=trace_id, network=network)
                response = problem(request, 403, "csrf_validation_failed", "Request origin or CSRF token is invalid.")
            if response is None and request.url.path != "/api/v1/auth/login":
                token = session_token(request)
                csrf = request.headers.get("x-csrf-token")
                if not token or not csrf or not service.validate_csrf(token, csrf):
                    event = "authentication.logout" if request.url.path == "/api/v1/auth/logout" else "csrf.denied"
                    service.audit_denial(event, token=token, trace_id=trace_id, network=network)
                    response = problem(request, 403, "csrf_validation_failed", "Request origin or CSRF token is invalid.")
        if response is None:
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
            await asyncio.wait_for(
                check_readiness(database_probe, storage_probe),
                timeout=settings.readiness_timeout_seconds,
            )
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
