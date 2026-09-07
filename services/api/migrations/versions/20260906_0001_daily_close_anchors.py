"""create immutable daily close anchors

Revision ID: 20260906_0001
Revises:
Create Date: 2026-09-06
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_0001"
down_revision: Optional[str] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.create_table(
        "daily_close_anchors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("relationship_id", sa.String(length=128), nullable=False),
        sa.Column("underlying_symbol", sa.String(length=16), nullable=False),
        sa.Column("leveraged_product_symbol", sa.String(length=16), nullable=False),
        sa.Column("signed_leverage", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("underlying_trading_date", sa.Date(), nullable=False),
        sa.Column("leveraged_product_trading_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("session_closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("underlying_close", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column(
            "leveraged_product_close", sa.Numeric(precision=20, scale=8), nullable=False
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("source_feed", sa.String(length=64), nullable=False),
        sa.Column(
            "underlying_market_timestamp", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "leveraged_product_market_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("underlying_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "leveraged_product_observed_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("underlying_quality", sa.String(length=16), nullable=False),
        sa.Column("leveraged_product_quality", sa.String(length=16), nullable=False),
        sa.Column("underlying_currency", sa.String(length=3), nullable=False),
        sa.Column("leveraged_product_currency", sa.String(length=3), nullable=False),
        sa.Column("underlying_message", sa.String(length=512), nullable=False),
        sa.Column("leveraged_product_message", sa.String(length=512), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("anchor_type", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "anchor_type = 'DAILY_CLOSE_ANCHOR'",
            name="ck_daily_close_anchor_type",
        ),
        sa.CheckConstraint(
            "signed_leverage <> 0",
            name="ck_daily_close_anchor_leverage_nonzero",
        ),
        sa.CheckConstraint(
            "underlying_close > 0 AND leveraged_product_close > 0",
            name="ck_daily_close_anchor_prices_positive",
        ),
        sa.CheckConstraint(
            "session_closed_at <= captured_at",
            name="ck_daily_close_anchor_session_complete",
        ),
        sa.CheckConstraint(
            "underlying_trading_date = trading_date "
            "AND leveraged_product_trading_date = trading_date",
            name="ck_daily_close_anchor_same_date",
        ),
        sa.CheckConstraint(
            "status = 'COMPLETE'",
            name="ck_daily_close_anchor_complete_only",
        ),
        sa.CheckConstraint(
            "underlying_symbol <> leveraged_product_symbol",
            name="ck_daily_close_anchor_symbols_differ",
        ),
        sa.CheckConstraint(
            "underlying_currency = 'USD' AND leveraged_product_currency = 'USD'",
            name="ck_daily_close_anchor_usd",
        ),
        sa.CheckConstraint("version > 0", name="ck_daily_close_anchor_version_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "underlying_symbol",
            "leveraged_product_symbol",
            "trading_date",
            name="uq_daily_close_anchor_logical_identity",
        ),
        sa.UniqueConstraint(
            "relationship_id",
            "trading_date",
            name="uq_daily_close_anchor_relationship_date",
        ),
        sa.UniqueConstraint(
            "relationship_id",
            "version",
            name="uq_daily_close_anchor_relationship_version",
        ),
    )
    op.create_index(
        "ix_daily_close_anchors_relationship_latest",
        "daily_close_anchors",
        ["relationship_id", "trading_date", "version"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION trafriend_reject_daily_close_anchor_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'daily_close_anchors rows are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER daily_close_anchors_immutable
        BEFORE UPDATE OR DELETE ON daily_close_anchors
        FOR EACH ROW
        EXECUTE FUNCTION trafriend_reject_daily_close_anchor_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER daily_close_anchors_immutable ON daily_close_anchors"
    )
    op.drop_index(
        "ix_daily_close_anchors_relationship_latest",
        table_name="daily_close_anchors",
    )
    op.drop_table("daily_close_anchors")
    op.execute("DROP FUNCTION trafriend_reject_daily_close_anchor_mutation()")
