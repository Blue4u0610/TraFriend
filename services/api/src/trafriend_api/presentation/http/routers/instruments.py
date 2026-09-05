
from fastapi import APIRouter, Depends, Query, Request

from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.presentation.http.dependencies import (
    get_market_data_service,
    response_meta,
)
from trafriend_api.presentation.http.schemas import (
    InstrumentCollectionResponse,
    InstrumentResponse,
    InstrumentSchema,
    LeveragedProductsData,
    LeveragedProductsResponse,
    RelationshipSchema,
)

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


@router.get("/search", response_model=InstrumentCollectionResponse)
def search_instruments(
    request: Request,
    query: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(10, ge=1, le=25),
    service: MarketDataService = Depends(get_market_data_service),
) -> InstrumentCollectionResponse:
    instruments = service.search_instruments(query=query, limit=limit)
    return InstrumentCollectionResponse(
        data=[InstrumentSchema.model_validate(item) for item in instruments],
        meta=response_meta(request, include_cursor=True),
    )


@router.get("/{instrument_id}", response_model=InstrumentResponse)
def get_instrument(
    instrument_id: str,
    request: Request,
    service: MarketDataService = Depends(get_market_data_service),
) -> InstrumentResponse:
    return InstrumentResponse(
        data=InstrumentSchema.model_validate(service.get_instrument(instrument_id)),
        meta=response_meta(request),
    )


@router.get(
    "/{instrument_id}/leveraged-products", response_model=LeveragedProductsResponse
)
def get_leveraged_products(
    instrument_id: str,
    request: Request,
    service: MarketDataService = Depends(get_market_data_service),
) -> LeveragedProductsResponse:
    selected = service.get_instrument(instrument_id)
    relationships = service.get_leveraged_relationships(instrument_id)
    if relationships:
        underlying = relationships[0].underlying
    else:
        underlying = selected
    return LeveragedProductsResponse(
        data=LeveragedProductsData(
            selected_instrument_id=selected.id,
            underlying=InstrumentSchema.model_validate(underlying),
            relationships=[
                RelationshipSchema.model_validate(item) for item in relationships
            ],
        ),
        meta=response_meta(request),
    )

