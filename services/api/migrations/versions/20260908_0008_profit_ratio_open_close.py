"""Separate QQQ membership, price captures and immutable ratio endpoints.

Revision ID: 20260908_0008
Revises: 20260907_0007
"""

from alembic import op
import sqlalchemy as sa

revision = "20260908_0008"
down_revision = "20260907_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qqq_constituent_snapshots",
        sa.Column("instrument_id", sa.String(100), primary_key=True),
        sa.Column("as_of", sa.Date(), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("source", sa.String(500), nullable=False),
        sa.UniqueConstraint("as_of", "symbol"),
    )
    op.create_table(
        "profit_ratio_capture_prices",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("instrument_id", sa.String(100), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("phase", sa.String(8), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("previous_close", sa.Numeric(), nullable=True),
        sa.Column("market_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("source_feed", sa.String(50), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.UniqueConstraint("instrument_id", "trading_date", "phase"),
        sa.CheckConstraint("phase IN ('OPEN', 'CLOSE')"),
        sa.CheckConstraint("price > 0 AND price < 10000000000000000"),
        sa.CheckConstraint(
            "previous_close IS NULL OR (previous_close > 0 AND previous_close < 10000000000000000)"
        ),
        sa.CheckConstraint("market_timestamp <= observed_at"),
        sa.CheckConstraint("currency = 'USD'"),
    )
    op.create_table(
        "profit_ratio_observations",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "price_id",
            sa.String(100),
            sa.ForeignKey("profit_ratio_capture_prices.id"),
            nullable=False,
        ),
        sa.Column("instrument_id", sa.String(100), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("phase", sa.String(8), nullable=False),
        sa.Column("ratio", sa.Numeric(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("methodology_key", sa.String(100), nullable=False),
        sa.Column("methodology_version", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "instrument_id",
            "trading_date",
            "phase",
            "methodology_key",
            "methodology_version",
            "version",
        ),
        sa.CheckConstraint("phase IN ('OPEN', 'CLOSE')"),
        sa.CheckConstraint("version > 0"),
        sa.CheckConstraint("ratio IS NULL OR (ratio >= 0 AND ratio <= 1)"),
        sa.CheckConstraint(
            "(status = 'DATA_INSUFFICIENT' AND ratio IS NULL) OR "
            "(status = 'ESTIMATED' AND ratio IS NOT NULL)"
        ),
    )
    for table in ("profit_ratio_capture_prices", "profit_ratio_observations"):
        for column in ("instrument_id", "trading_date"):
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.execute("""
        CREATE FUNCTION reject_profit_ratio_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'Profit Ratio history is immutable; append a reviewed revision';
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in (
        "profit_ratio_capture_prices",
        "profit_ratio_observations",
        "qqq_constituent_snapshots",
    ):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_profit_ratio_mutation()"
        )


def downgrade() -> None:
    for table in (
        "profit_ratio_observations",
        "profit_ratio_capture_prices",
        "qqq_constituent_snapshots",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_profit_ratio_mutation()")
