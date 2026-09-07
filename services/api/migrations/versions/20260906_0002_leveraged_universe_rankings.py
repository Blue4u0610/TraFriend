"""create leveraged universe and market ranking tables

Revision ID: 20260906_0002
Revises: 20260906_0001
Create Date: 2026-09-06
"""

from datetime import date, datetime, timezone
from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_0002"
down_revision: Optional[str] = "20260906_0001"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

VERIFIED_AT = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)


def upgrade() -> None:
    underlyings = op.create_table(
        "underlyings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("instrument_type", sa.String(length=32), nullable=False),
        sa.Column("exchange_mic", sa.String(length=8), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("profit_ratio_available", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("symbol = UPPER(symbol)", name="ck_underlying_symbol_upper"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol"),
    )
    leveraged_products = op.create_table(
        "leveraged_products",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("relationship_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("exchange_mic", sa.String(length=8), nullable=False),
        sa.Column("underlying_id", sa.String(length=64), nullable=False),
        sa.Column("signed_leverage", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("issuer", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("objective_period", sa.String(length=16), nullable=False),
        sa.Column("authoritative_source", sa.String(length=1024), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction IN ('LONG', 'INVERSE')",
            name="ck_leveraged_product_direction",
        ),
        sa.CheckConstraint(
            "(direction = 'LONG' AND signed_leverage > 0) OR "
            "(direction = 'INVERSE' AND signed_leverage < 0)",
            name="ck_leveraged_product_direction_matches_leverage",
        ),
        sa.CheckConstraint(
            "signed_leverage <> 0", name="ck_leveraged_product_leverage_nonzero"
        ),
        sa.CheckConstraint(
            "symbol = UPPER(symbol)", name="ck_leveraged_symbol_upper"
        ),
        sa.ForeignKeyConstraint(
            ["underlying_id"], ["underlyings.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("relationship_id"),
        sa.UniqueConstraint("symbol"),
    )
    op.create_index(
        op.f("ix_leveraged_products_underlying_id"),
        "leveraged_products",
        ["underlying_id"],
        unique=False,
    )
    op.create_table(
        "market_rankings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ranking_period", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_status", sa.String(length=32), nullable=False),
        sa.Column("ranking_type", sa.String(length=64), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("trading_metric", sa.Numeric(precision=30, scale=4), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=256), nullable=False),
        sa.CheckConstraint(
            "period_status IN ('SEPTEMBER_TO_DATE', 'FINAL')",
            name="ck_market_ranking_period_status",
        ),
        sa.CheckConstraint(
            "rank BETWEEN 1 AND 100", name="ck_market_ranking_rank"
        ),
        sa.CheckConstraint(
            "trading_metric >= 0", name="ck_market_ranking_metric_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ranking_period",
            "ranking_type",
            "rank",
            name="uq_market_ranking_period_type_rank",
        ),
        sa.UniqueConstraint(
            "ranking_period",
            "ranking_type",
            "symbol",
            name="uq_market_ranking_period_type_symbol",
        ),
    )

    op.bulk_insert(
        underlyings,
        [
            _underlying("ins_sndk_xnas", "SNDK", "Sandisk Corporation", "stock"),
            _underlying("ins_nvda_xnas", "NVDA", "NVIDIA Corporation", "stock", True),
            _underlying("ins_tsla_xnas", "TSLA", "Tesla, Inc.", "stock"),
            _underlying("ins_qqq_xnas", "QQQ", "Invesco QQQ Trust", "etf", True),
            _underlying("ins_soxx_xnas", "SOXX", "iShares Semiconductor ETF", "etf"),
        ],
    )
    op.bulk_insert(
        leveraged_products,
        [
            _product(
                "ins_snxx_xnas",
                "rel_sndk_snxx_2x",
                "SNXX",
                "Tradr 2X Long SNDK Daily ETF",
                "BATS",
                "ins_sndk_xnas",
                "2",
                "Tradr ETFs",
                "LONG",
                "https://www.sec.gov/Archives/edgar/data/1587982/000121390026008044/ea0273211-04_497k.htm",
                date(2026, 1, 26),
            ),
            _product(
                "ins_nvdl_xnas",
                "rel_nvda_nvdl_2x",
                "NVDL",
                "GraniteShares 2x Long NVDA Daily ETF",
                "XNAS",
                "ins_nvda_xnas",
                "2",
                "GraniteShares",
                "LONG",
                "https://graniteshares.com/etfs/nvdl/",
                date(2022, 12, 13),
            ),
            _product(
                "ins_tsll_xnas",
                "rel_tsla_tsll_2x",
                "TSLL",
                "Direxion Daily TSLA Bull 2X ETF",
                "XNAS",
                "ins_tsla_xnas",
                "2",
                "Direxion",
                "LONG",
                "https://www.direxion.com/product/daily-tsla-bull-and-bear-leveraged-single-stock-etfs",
                date(2022, 8, 9),
            ),
            _product(
                "ins_qld_xnas",
                "rel_qqq_qld_2x",
                "QLD",
                "ProShares Ultra QQQ",
                "XNAS",
                "ins_qqq_xnas",
                "2",
                "ProShares",
                "LONG",
                "https://www.proshares.com/our-etfs/leveraged-and-inverse/qld",
                date(2006, 6, 19),
            ),
            _product(
                "ins_tqqq_xnas",
                "rel_qqq_tqqq_3x",
                "TQQQ",
                "ProShares UltraPro QQQ",
                "XNAS",
                "ins_qqq_xnas",
                "3",
                "ProShares",
                "LONG",
                "https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq",
                date(2010, 2, 9),
            ),
            _product(
                "ins_sqqq_xnas",
                "rel_qqq_sqqq_n3x",
                "SQQQ",
                "ProShares UltraPro Short QQQ",
                "XNAS",
                "ins_qqq_xnas",
                "-3",
                "ProShares",
                "INVERSE",
                "https://www.proshares.com/our-etfs/leveraged-and-inverse/sqqq",
                date(2010, 2, 9),
            ),
            _product(
                "ins_soxl_arcx",
                "rel_soxx_soxl_3x",
                "SOXL",
                "Direxion Daily Semiconductor Bull 3X ETF",
                "ARCX",
                "ins_soxx_xnas",
                "3",
                "Direxion",
                "LONG",
                "https://www.direxion.com/product/daily-semiconductor-bull-bear-3x-etfs",
                date(2010, 3, 11),
            ),
            _product(
                "ins_soxs_arcx",
                "rel_soxx_soxs_n3x",
                "SOXS",
                "Direxion Daily Semiconductor Bear 3X ETF",
                "ARCX",
                "ins_soxx_xnas",
                "-3",
                "Direxion",
                "INVERSE",
                "https://www.direxion.com/product/daily-semiconductor-bull-bear-3x-etfs",
                date(2010, 3, 11),
            ),
        ],
    )


def _underlying(
    instrument_id: str,
    symbol: str,
    name: str,
    instrument_type: str,
    profit_ratio: bool = False,
) -> dict[str, object]:
    return {
        "id": instrument_id,
        "symbol": symbol,
        "display_name": name,
        "instrument_type": instrument_type,
        "exchange_mic": "XNAS",
        "currency": "USD",
        "active": True,
        "profit_ratio_available": profit_ratio,
        "created_at": VERIFIED_AT,
        "updated_at": VERIFIED_AT,
    }


def _product(
    instrument_id: str,
    relationship_id: str,
    symbol: str,
    name: str,
    exchange_mic: str,
    underlying_id: str,
    leverage: str,
    issuer: str,
    direction: str,
    source: str,
    effective_from: date,
) -> dict[str, object]:
    return {
        "id": instrument_id,
        "relationship_id": relationship_id,
        "symbol": symbol,
        "display_name": name,
        "exchange_mic": exchange_mic,
        "underlying_id": underlying_id,
        "signed_leverage": leverage,
        "issuer": issuer,
        "direction": direction,
        "active": True,
        "objective_period": "daily",
        "authoritative_source": source,
        "verified_at": VERIFIED_AT,
        "effective_from": effective_from,
        "effective_to": None,
        "created_at": VERIFIED_AT,
        "updated_at": VERIFIED_AT,
    }


def downgrade() -> None:
    op.drop_table("market_rankings")
    op.drop_index(
        op.f("ix_leveraged_products_underlying_id"),
        table_name="leveraged_products",
    )
    op.drop_table("leveraged_products")
    op.drop_table("underlyings")
