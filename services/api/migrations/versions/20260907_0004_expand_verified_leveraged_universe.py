"""expand the verified leveraged-product universe

Revision ID: 20260907_0004
Revises: 20260906_0003
Create Date: 2026-09-07

The rows below are a point-in-time catalog snapshot. Relationships were checked
against issuer product pages and the products were confirmed active/tradable in
Alpaca's U.S. equity asset catalog. ``effective_from`` is the first date this
snapshot is valid for TraFriend; it is not presented as the fund inception date.
"""

from datetime import date, datetime, timezone
from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert

revision: str = "20260907_0004"
down_revision: Optional[str] = "20260906_0003"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

VERIFIED_AT = datetime(2026, 9, 7, 16, tzinfo=timezone.utc)
EFFECTIVE_FROM = date(2026, 9, 4)

ISSUER_SOURCES = {
    "Corgi": "https://corgiinvest.com/2xleveraged",
    "Defiance": "https://www.defianceetfs.com/muz/",
    "Direxion": "https://www.direxion.com/single-stock-etfs",
    "GraniteShares": "https://graniteshares.com/etfs/leveraged/",
    "Leverage Shares": "https://leverageshares.com/us/all-etfs?category=Daily+Leveraged",
    "ProShares": "https://www.proshares.com/our-etfs/find-leveraged-and-inverse-etfs",
    "T-REX": "https://www.rexshares.com/home-2/all-funds/?llm_view=1&tm=tt",
    "Tradr ETFs": "https://www.tradretfs.com/",
}

UNDERLYINGS = (
    ("ins_mu_xnas", "MU", "Micron Technology, Inc.", "stock", "XNAS"),
    ("ins_nvda_xnas", "NVDA", "NVIDIA Corporation", "stock", "XNAS"),
    ("ins_qqq_xnas", "QQQ", "Invesco QQQ Trust", "etf", "XNAS"),
    ("ins_sndk_xnas", "SNDK", "Sandisk Corporation", "stock", "XNAS"),
    ("ins_soxx_xnas", "SOXX", "iShares Semiconductor ETF", "etf", "XNAS"),
    ("ins_tsla_xnas", "TSLA", "Tesla, Inc.", "stock", "XNAS"),
)

# (symbol, name, exchange MIC, underlying id, leverage, issuer)
PRODUCTS = (
    ("MIC", "Corgi MU 2x Daily ETF", "BATS", "ins_mu_xnas", "2", "Corgi"),
    ("MUU", "Direxion Daily MU Bull 2X ETF", "XNAS", "ins_mu_xnas", "2", "Direxion"),
    ("MUD", "Direxion Daily MU Bear 1X ETF", "XNAS", "ins_mu_xnas", "-1", "Direxion"),
    ("MULL", "GraniteShares 2x Long MU Daily ETF", "XNAS", "ins_mu_xnas", "2", "GraniteShares"),
    ("MUG", "Leverage Shares 2X Long MU Daily ETF", "BATS", "ins_mu_xnas", "2", "Leverage Shares"),
    ("MUZ", "Defiance Daily Target 2X Short MU ETF", "ARCX", "ins_mu_xnas", "-2", "Defiance"),
    ("NVDL", "GraniteShares 2x Long NVDA Daily ETF", "XNAS", "ins_nvda_xnas", "2", "GraniteShares"),
    ("NVC", "Corgi NVDA 2x Daily ETF", "BATS", "ins_nvda_xnas", "2", "Corgi"),
    (
        "NVD",
        "GraniteShares 2x Short NVDA Daily ETF",
        "XNAS",
        "ins_nvda_xnas",
        "-2",
        "GraniteShares",
    ),
    ("NVDU", "Direxion Daily NVDA Bull 2X ETF", "XNAS", "ins_nvda_xnas", "2", "Direxion"),
    ("NVDD", "Direxion Daily NVDA Bear 1X ETF", "XNAS", "ins_nvda_xnas", "-1", "Direxion"),
    ("NVDS", "Tradr 1.5X Short NVDA Daily ETF", "XNAS", "ins_nvda_xnas", "-1.5", "Tradr ETFs"),
    ("NVDX", "T-REX 2X Long NVIDIA Daily Target ETF", "BATS", "ins_nvda_xnas", "2", "T-REX"),
    ("NVDQ", "T-REX 2X Inverse NVIDIA Daily Target ETF", "BATS", "ins_nvda_xnas", "-2", "T-REX"),
    ("NVDB", "ProShares Ultra NVDA", "ARCX", "ins_nvda_xnas", "2", "ProShares"),
    (
        "NVDG",
        "Leverage Shares 2X Long NVDA Daily ETF",
        "XNAS",
        "ins_nvda_xnas",
        "2",
        "Leverage Shares",
    ),
    ("QLD", "ProShares Ultra QQQ", "ARCX", "ins_qqq_xnas", "2", "ProShares"),
    ("TQQQ", "ProShares UltraPro QQQ", "XNAS", "ins_qqq_xnas", "3", "ProShares"),
    ("SQQQ", "ProShares UltraPro Short QQQ", "XNAS", "ins_qqq_xnas", "-3", "ProShares"),
    ("PSQ", "ProShares Short QQQ", "ARCX", "ins_qqq_xnas", "-1", "ProShares"),
    ("QID", "ProShares UltraShort QQQ", "ARCX", "ins_qqq_xnas", "-2", "ProShares"),
    ("SNXX", "Tradr 2X Long SNDK Daily ETF", "BATS", "ins_sndk_xnas", "2", "Tradr ETFs"),
    ("SNDC", "Corgi SNDK 2x Daily ETF", "BATS", "ins_sndk_xnas", "2", "Corgi"),
    ("SNDQ", "Tradr 2X Short SNDK Daily ETF", "BATS", "ins_sndk_xnas", "-2", "Tradr ETFs"),
    ("SNDU", "T-REX 2X Long SNDK Daily Target ETF", "BATS", "ins_sndk_xnas", "2", "T-REX"),
    (
        "SNDG",
        "Leverage Shares 2X Long SNDK Daily ETF",
        "BATS",
        "ins_sndk_xnas",
        "2",
        "Leverage Shares",
    ),
    ("SOXL", "Direxion Daily Semiconductor Bull 3X ETF", "ARCX", "ins_soxx_xnas", "3", "Direxion"),
    ("SOXS", "Direxion Daily Semiconductor Bear 3X ETF", "ARCX", "ins_soxx_xnas", "-3", "Direxion"),
    ("TSLL", "Direxion Daily TSLA Bull 2X ETF", "XNAS", "ins_tsla_xnas", "2", "Direxion"),
    ("TESC", "Corgi TSLA 2x Daily ETF", "BATS", "ins_tsla_xnas", "2", "Corgi"),
    ("TSLS", "Direxion Daily TSLA Bear 1X ETF", "XNAS", "ins_tsla_xnas", "-1", "Direxion"),
    ("TSLQ", "Tradr 2X Short TSLA Daily ETF", "XNAS", "ins_tsla_xnas", "-2", "Tradr ETFs"),
    ("TSLT", "T-REX 2X Long Tesla Daily Target ETF", "BATS", "ins_tsla_xnas", "2", "T-REX"),
    ("TSLZ", "T-REX 2X Inverse Tesla Daily Target ETF", "BATS", "ins_tsla_xnas", "-2", "T-REX"),
    ("TSLI", "ProShares Ultra TSLA", "ARCX", "ins_tsla_xnas", "2", "ProShares"),
    (
        "TSDD",
        "GraniteShares 2x Short TSLA Daily ETF",
        "XNAS",
        "ins_tsla_xnas",
        "-2",
        "GraniteShares",
    ),
    (
        "TSL",
        "GraniteShares 1.25x Long TSLA Daily ETF",
        "XNAS",
        "ins_tsla_xnas",
        "1.25",
        "GraniteShares",
    ),
    ("TSLR", "GraniteShares 2x Long TSLA Daily ETF", "XNAS", "ins_tsla_xnas", "2", "GraniteShares"),
    (
        "TSLG",
        "Leverage Shares 2X Long TSLA Daily ETF",
        "XNAS",
        "ins_tsla_xnas",
        "2",
        "Leverage Shares",
    ),
)

ORIGINAL_PRODUCT_SYMBOLS = {
    "NVDL",
    "QLD",
    "SNXX",
    "SOXL",
    "SOXS",
    "SQQQ",
    "TQQQ",
    "TSLL",
}


def upgrade() -> None:
    underlyings = sa.table(
        "underlyings",
        sa.column("id", sa.String),
        sa.column("symbol", sa.String),
        sa.column("display_name", sa.String),
        sa.column("instrument_type", sa.String),
        sa.column("exchange_mic", sa.String),
        sa.column("currency", sa.String),
        sa.column("active", sa.Boolean),
        sa.column("profit_ratio_available", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    products = sa.table(
        "leveraged_products",
        sa.column("id", sa.String),
        sa.column("relationship_id", sa.String),
        sa.column("symbol", sa.String),
        sa.column("display_name", sa.String),
        sa.column("exchange_mic", sa.String),
        sa.column("underlying_id", sa.String),
        sa.column("signed_leverage", sa.Numeric),
        sa.column("issuer", sa.String),
        sa.column("direction", sa.String),
        sa.column("active", sa.Boolean),
        sa.column("objective_period", sa.String),
        sa.column("authoritative_source", sa.String),
        sa.column("verified_at", sa.DateTime(timezone=True)),
        sa.column("effective_from", sa.Date),
        sa.column("effective_to", sa.Date),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    underlying_rows = [
        {
            "id": item[0],
            "symbol": item[1],
            "display_name": item[2],
            "instrument_type": item[3],
            "exchange_mic": item[4],
            "currency": "USD",
            "active": True,
            "profit_ratio_available": item[1] in {"NVDA", "QQQ"},
            "created_at": VERIFIED_AT,
            "updated_at": VERIFIED_AT,
        }
        for item in UNDERLYINGS
    ]
    connection.execute(
        insert(underlyings)
        .values(underlying_rows)
        .on_conflict_do_nothing(index_elements=["symbol"])
    )
    product_rows = [_product_row(*item) for item in PRODUCTS]
    connection.execute(
        insert(products)
        .values(product_rows)
        .on_conflict_do_nothing(index_elements=["symbol"])
    )


def _product_row(
    symbol: str,
    name: str,
    exchange_mic: str,
    underlying_id: str,
    leverage: str,
    issuer: str,
) -> dict[str, object]:
    underlying_symbol = underlying_id.removeprefix("ins_").split("_")[0]
    leverage_id = leverage.replace("-", "n").replace(".", "p")
    return {
        "id": f"ins_{symbol.lower()}_{exchange_mic.lower()}",
        "relationship_id": (
            f"rel_{underlying_symbol}_{symbol.lower()}_{leverage_id}x"
        ),
        "symbol": symbol,
        "display_name": name,
        "exchange_mic": exchange_mic,
        "underlying_id": underlying_id,
        "signed_leverage": leverage,
        "issuer": issuer,
        "direction": "LONG" if not leverage.startswith("-") else "INVERSE",
        "active": True,
        "objective_period": "daily",
        "authoritative_source": ISSUER_SOURCES[issuer],
        "verified_at": VERIFIED_AT,
        "effective_from": EFFECTIVE_FROM,
        "effective_to": None,
        "created_at": VERIFIED_AT,
        "updated_at": VERIFIED_AT,
    }


def downgrade() -> None:
    new_symbols = sorted({item[0] for item in PRODUCTS} - ORIGINAL_PRODUCT_SYMBOLS)
    products = sa.table("leveraged_products", sa.column("symbol", sa.String))
    op.execute(products.delete().where(products.c.symbol.in_(new_symbols)))
    op.execute(sa.text("DELETE FROM underlyings WHERE symbol = 'MU'"))
