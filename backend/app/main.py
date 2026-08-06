"""
Healthy Harvest API - application entry point.

Phase 2 scope: authentication routes (register, with login/logout/refresh
following in later milestones) plus the app-wide exception handlers that
give every endpoint - success or failure - the same response envelope.
"""
from slowapi.errors import RateLimitExceeded
from app.core.rate_limit import limiter
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.core.config import settings
from app.core.exceptions import DomainError

app = FastAPI(
    title=settings.APP_NAME,
    description="E-commerce API for Healthy Harvest - cereals, ready mixes, and healthy foods.",
    version="0.1.0",
)
# Registers the shared limiter (app/core/rate_limit.py) on app.state so
# slowapi's internals can find it via `request.app.state.limiter` - this
# is required regardless of which routes actually use `@limiter.limit(...)`.
app.state.limiter = limiter


# Allow the Next.js frontend (and any other configured origins) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


# --- Exception handlers -----------------------------------------------
# These three handlers are what make EVERY error response - regardless of
# where it came from (a service raising a DomainError, a route raising
# HTTPException, or Pydantic rejecting a bad request body) - come back as
# {"success": false, "message": "..."} instead of FastAPI's differently
# shaped defaults. Route handlers never need to build an error response
# themselves; they just raise, and one of these three catches it.

@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Catches every business-rule violation raised by the service layer
    (DuplicateEmailError, DuplicatePhoneError, and whatever Milestone 4+
    adds) - each exception carries its own `http_status`, so this handler
    never needs to change when a new domain error is introduced."""
    return JSONResponse(
        status_code=exc.http_status,
        content={"success": False, "message": exc.message},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Catches ordinary `raise HTTPException(...)` calls (404s, 401s from
    Milestone 5's auth dependency, etc.) and reshapes FastAPI's default
    `{"detail": "..."}` into the project's `{"success", "message"}` envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Catches Pydantic/FastAPI request-validation failures (missing
    fields, a password that fails the strength check, phone_number not
    matching the pattern, passwords that don't match, etc). `message` is
    a single human-readable summary of the first error; the full
    structured list stays available under `errors` for clients that want
    to highlight specific fields.

    IMPORTANT: when a validator raises a plain `ValueError` (as our
    password-strength and confirm_password checks do), Pydantic's error
    dict includes the *raw exception object* under `ctx.error` - which is
    not JSON serializable and would otherwise crash this handler itself
    (turning an intended 422 into an unhandled 500). `ctx` is stripped
    below since `msg` already has the human-readable text clients need;
    `jsonable_encoder` is then run as a defensive second pass in case any
    other non-serializable value ever ends up in an error dict.
    """
    first_error = exc.errors()[0]
    field_path = ".".join(str(loc) for loc in first_error["loc"] if loc != "body")
    message = f"{field_path}: {first_error['msg']}" if field_path else first_error["msg"]

    safe_errors = jsonable_encoder(
        [{key: value for key, value in error.items() if key != "ctx"} for error in exc.errors()]
    )

    return JSONResponse(
        status_code=422,
        content={"success": False, "message": message, "errors": safe_errors},
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Replaces slowapi's default `{"error": "..."}` body with this
    project's `{"success": false, "message": "..."}` envelope, so a 429
    looks like every other error response instead of a one-off shape.
    Still delegates to the limiter's own `_inject_headers` so the
    `Retry-After` / `X-RateLimit-*` headers get set correctly - only the
    JSON body is customized here."""
    response = JSONResponse(
        status_code=429,
        content={"success": False, "message": "Too many attempts. Please try again later."},
    )
    response = request.app.state.limiter._inject_headers(response, request.state.view_rate_limit)
    return response


@app.get("/", tags=["Health"])
def read_root() -> dict:
    """Basic health check used to confirm the API is up and reachable."""
    return {"status": "healthy", "message": "Healthy Harvest API Running"}