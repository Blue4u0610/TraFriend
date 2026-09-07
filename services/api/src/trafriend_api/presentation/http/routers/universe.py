from typing import Literal, cast

from fastapi import APIRouter, Depends, Query, Request

from trafriend_api.application.services.universe import (
    UnderlyingWorkspace,
    UniverseService,
)
from trafriend_api.domain.errors import ResourceNotFoundError
from trafriend_api.domain.universe import RankingType
from trafriend_api.presentation.http.dependencies import (
    get_universe_service,
    response_meta,
)
from trafriend_api.presentation.http.schemas import (
    AnchorResolutionSchema,
    DailyCloseAnchorSchema,
    InstrumentCollectionResponse,
    InstrumentSchema,
    MultiCalculationData,
    MultiCalculationRequest,
    MultiCalculationResponse,
    MultiCalculationRowSchema,
    PopularData,
    PopularResponse,
    PopularRowSchema,
    RelationshipSchema,
    UnderlyingWorkspaceData,
    UnderlyingWorkspaceResponse,
)

router = APIRouter(prefix="/api/v1", tags=["universe"])


@router.get("/universe/search", response_model=InstrumentCollectionResponse)
def search_universe(
    request: Request,
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(10, ge=1, le=25),
    service: UniverseService = Depends(get_universe_service),
) -> InstrumentCollectionResponse:
    return InstrumentCollectionResponse(
        data=[InstrumentSchema.model_validate(item) for item in service.search(q, limit)],
        meta=response_meta(request, include_cursor=True),
    )


@router.get(
    "/universe/underlyings/search",
    response_model=InstrumentCollectionResponse,
)
def search_underlyings(
    request: Request,
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(10, ge=1, le=25),
    service: UniverseService = Depends(get_universe_service),
) -> InstrumentCollectionResponse:
    return InstrumentCollectionResponse(
        data=[
            InstrumentSchema.model_validate(item)
            for item in service.search_underlyings(q, limit)
        ],
        meta=response_meta(request, include_cursor=True),
    )


@router.get(
    "/universe/leveraged-products/search",
    response_model=InstrumentCollectionResponse,
)
def search_leveraged_products(
    request: Request,
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(10, ge=1, le=25),
    service: UniverseService = Depends(get_universe_service),
) -> InstrumentCollectionResponse:
    return InstrumentCollectionResponse(
        data=[
            InstrumentSchema.model_validate(item)
            for item in service.search_leveraged_products(q, limit)
        ],
        meta=response_meta(request, include_cursor=True),
    )


@router.get("/underlyings/{symbol}", response_model=UnderlyingWorkspaceResponse)
def get_underlying(
    symbol: str,
    request: Request,
    service: UniverseService = Depends(get_universe_service),
) -> UnderlyingWorkspaceResponse:
    return _workspace_response(service.resolve(symbol, capture_missing=False), request)


@router.get(
    "/underlyings/{symbol}/leveraged-products",
    response_model=UnderlyingWorkspaceResponse,
)
def get_underlying_products(
    symbol: str,
    request: Request,
    service: UniverseService = Depends(get_universe_service),
) -> UnderlyingWorkspaceResponse:
    return _workspace_response(service.resolve(symbol, capture_missing=False), request)


@router.post(
    "/underlyings/{symbol}/resolve",
    response_model=UnderlyingWorkspaceResponse,
)
def resolve_underlying(
    symbol: str,
    request: Request,
    service: UniverseService = Depends(get_universe_service),
) -> UnderlyingWorkspaceResponse:
    return _workspace_response(service.resolve(symbol, capture_missing=True), request)


@router.post(
    "/underlyings/{symbol}/calculations",
    response_model=MultiCalculationResponse,
)
def calculate_all_products(
    symbol: str,
    payload: MultiCalculationRequest,
    request: Request,
    service: UniverseService = Depends(get_universe_service),
) -> MultiCalculationResponse:
    calculation = service.calculate_all(symbol, payload.target_price)
    rows = []
    for row in calculation.rows:
        rows.append(
            MultiCalculationRowSchema(
                relationship=RelationshipSchema.model_validate(row.relationship),
                status=cast(Literal["AVAILABLE", "UNAVAILABLE"], row.status),
                anchor=(
                    None
                    if row.anchor is None
                    else DailyCloseAnchorSchema.model_validate(row.anchor)
                ),
                theoretical_target_price=(
                    None if row.result is None else row.result.theoretical_target_price
                ),
                underlying_return=(
                    None if row.result is None else row.result.underlying_return
                ),
                leveraged_return=(
                    None if row.result is None else row.result.leveraged_return
                ),
                message=row.message,
            )
        )
    return MultiCalculationResponse(
        data=MultiCalculationData(
            underlying=InstrumentSchema.model_validate(calculation.underlying),
            target_price=calculation.target_price,
            rows=rows,
            formula_version="leveraged-daily-close-linear/v2",
        ),
        meta=response_meta(request),
    )


@router.get("/popular", response_model=PopularResponse)
def get_popular(
    request: Request,
    ranking_period: str = Query("2026-09", pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(100, ge=1, le=100),
    service: UniverseService = Depends(get_universe_service),
) -> PopularResponse:
    dataset = service.popular(
        ranking_period=ranking_period,
        ranking_type=RankingType.DOLLAR_TRADING_VOLUME,
        limit=limit,
    )
    rows = []
    for row in dataset.rows:
        name = row.display_name or None
        supported = 0
        try:
            underlying = service.get_underlying(row.symbol)
            name = name or underlying.name
            supported = len(service.relationships(row.symbol))
        except ResourceNotFoundError:
            pass
        rows.append(
            PopularRowSchema(
                rank=row.rank,
                symbol=row.symbol,
                name=name,
                trading_metric=row.trading_metric,
                calculated_at=row.calculated_at,
                source=row.source,
                completeness_status=row.completeness_status.value,
                sessions_observed=row.sessions_observed,
                sessions_expected=row.sessions_expected,
                supported_leveraged_products=supported,
            )
        )
    return PopularResponse(
        data=PopularData(
            ranking_period=dataset.ranking_period,
            period_status=cast(
                Literal["SEPTEMBER_TO_DATE", "MONTH_TO_DATE", "FINAL"],
                dataset.period_status.value,
            ),
            ranking_type="DOLLAR_TRADING_VOLUME",
            population_status=cast(
                Literal["COMPLETE", "PARTIAL", "NOT_POPULATED"],
                dataset.population_status.value,
            ),
            rows=rows,
        ),
        meta=response_meta(request),
    )


def _workspace_response(
    workspace: UnderlyingWorkspace, request: Request
) -> UnderlyingWorkspaceResponse:
    return UnderlyingWorkspaceResponse(
        data=UnderlyingWorkspaceData(
            underlying=InstrumentSchema.model_validate(workspace.underlying),
            rows=[
                AnchorResolutionSchema(
                    relationship=RelationshipSchema.model_validate(row.relationship),
                    status=cast(Literal["AVAILABLE", "UNAVAILABLE"], row.status),
                    anchor_source=cast(
                        Literal["CACHE", "ON_DEMAND", "NONE"], row.anchor_source
                    ),
                    message=row.message,
                    anchor=(
                        None
                        if row.anchor is None
                        else DailyCloseAnchorSchema.model_validate(row.anchor)
                    ),
                )
                for row in workspace.rows
            ],
        ),
        meta=response_meta(request),
    )
