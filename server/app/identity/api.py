from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from server.app.identity.service import AuthenticationFailed, CsrfFailed, IdentityService, InvalidSession


COOKIE_NAME = "__Host-hr_session"
router = APIRouter(prefix="/api/v1")


class LoginRequest(BaseModel):
    organization_slug: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def validate_email_shape(cls, value: str) -> str:
        if value.count("@") != 1 or not all(value.split("@")):
            raise ValueError("invalid email address")
        return value


def problem(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={"type": "about:blank", "title": "Request denied", "status": status, "detail": detail, "code": code, "trace_id": request.state.trace_id, "errors": []},
    )


def allowed_origin(request: Request) -> bool:
    return request.headers.get("origin") in request.app.state.settings.cors_origins


@router.post("/auth/login")
def login(payload: LoginRequest, request: Request):
    if not allowed_origin(request):
        return problem(request, 403, "csrf_validation_failed", "Request origin or CSRF token is invalid.")
    service: IdentityService = request.app.state.identity_service
    try:
        session_token, csrf = service.login(payload.organization_slug, payload.email, payload.password, trace_id=request.state.trace_id, network=request.headers.get("x-forwarded-for") or request.client.host if request.client else None)
    except AuthenticationFailed:
        return problem(request, 401, "authentication_failed", "Invalid credentials or account unavailable.")
    response = JSONResponse({"data": {"authenticated": True}})
    response.set_cookie(COOKIE_NAME, session_token, httponly=True, secure=request.app.state.settings.environment == "production", samesite="lax", path="/")
    response.headers["X-CSRF-Token"] = csrf
    return response


@router.get("/me")
def me(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return problem(request, 401, "authentication_required", "Authentication is required.")
    try:
        data, csrf = request.app.state.identity_service.me(token)
    except InvalidSession:
        return problem(request, 401, "authentication_required", "Authentication is required.")
    response = JSONResponse({"data": data})
    response.headers["X-CSRF-Token"] = csrf
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/auth/logout", status_code=204)
def logout(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    csrf = request.headers.get("x-csrf-token")
    if not token or not csrf or not allowed_origin(request):
        return problem(request, 403, "csrf_validation_failed", "Request origin or CSRF token is invalid.")
    try:
        request.app.state.identity_service.logout(token, csrf, trace_id=request.state.trace_id, network=request.headers.get("x-forwarded-for") or request.client.host if request.client else None)
    except CsrfFailed:
        return problem(request, 403, "csrf_validation_failed", "Request origin or CSRF token is invalid.")
    except InvalidSession:
        return problem(request, 401, "authentication_required", "Authentication is required.")
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/", secure=request.app.state.settings.environment == "production", httponly=True, samesite="lax")
    return response
