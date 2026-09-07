from __future__ import annotations

from typing import Awaitable, Callable, Optional
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from trafriend_api.domain.errors import (
    AnchorUnavailableError,
    AnchorVersionInactiveError,
    CalculationOutOfDomainError,
    FinancialInputError,
    ResourceNotFoundError,
    UnsupportedFeatureError,
)
from trafriend_api.presentation.http.dependencies import build_application_services
from trafriend_api.presentation.http.routers import (
    health,
    instruments,
    leveraged_etf,
    profit_ratio,
    universe,
)
from trafriend_api.settings import Settings


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    app_settings = settings or Settings.from_environment()
    app = FastAPI(
        title="TraFriend API",
        version="0.1.0",
        description="Mock-first market analytics API for TraFriend Phase 1.",
    )
    services = build_application_services(app_settings)
    app.state.market_data_service = services.market_data
    app.state.universe_service = services.universe

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def add_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    def problem(
        request: Request, status: int, code: str, title: str, detail: str
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            media_type="application/problem+json",
            content={
                "type": f"https://trafriend.example/problems/{code.lower().replace('_', '-')}",
                "title": title,
                "status": status,
                "detail": detail,
                "instance": request.url.path,
                "code": code,
                "request_id": request.state.request_id,
                "errors": [],
            },
        )

    @app.exception_handler(ResourceNotFoundError)
    async def not_found_handler(
        request: Request, exc: ResourceNotFoundError
    ) -> JSONResponse:
        return problem(request, 404, "RESOURCE_NOT_FOUND", "Resource not found", str(exc))

    @app.exception_handler(UnsupportedFeatureError)
    async def unsupported_handler(
        request: Request, exc: UnsupportedFeatureError
    ) -> JSONResponse:
        return problem(
            request,
            422,
            "PROFIT_RATIO_UNSUPPORTED",
            "Profit Ratio unsupported",
            str(exc),
        )

    @app.exception_handler(AnchorVersionInactiveError)
    async def inactive_anchor_handler(
        request: Request, exc: AnchorVersionInactiveError
    ) -> JSONResponse:
        return problem(
            request,
            409,
            "ANCHOR_VERSION_INACTIVE",
            "Daily Close Anchor changed",
            str(exc),
        )

    @app.exception_handler(AnchorUnavailableError)
    async def unavailable_anchor_handler(
        request: Request, exc: AnchorUnavailableError
    ) -> JSONResponse:
        return problem(
            request,
            503,
            "ANCHOR_UNAVAILABLE",
            "Daily Close Anchor unavailable",
            str(exc),
        )

    @app.exception_handler(CalculationOutOfDomainError)
    async def calculation_domain_handler(
        request: Request, exc: CalculationOutOfDomainError
    ) -> JSONResponse:
        return problem(
            request,
            422,
            "CALCULATION_OUT_OF_DOMAIN",
            "Target is outside the model domain",
            str(exc),
        )

    @app.exception_handler(FinancialInputError)
    async def financial_input_handler(
        request: Request, exc: FinancialInputError
    ) -> JSONResponse:
        return problem(
            request,
            422,
            "VALIDATION_ERROR",
            "Invalid financial input",
            str(exc),
        )

    app.include_router(health.router)
    app.include_router(instruments.router)
    app.include_router(leveraged_etf.router)
    app.include_router(profit_ratio.router)
    app.include_router(universe.router)
    return app


app = create_app()
