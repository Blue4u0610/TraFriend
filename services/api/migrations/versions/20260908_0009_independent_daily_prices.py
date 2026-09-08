"""Independent immutable daily price candles, unrelated to Profit Ratio availability.

Revision ID: 20260908_0009
Revises: 20260908_0008
"""

from alembic import op
import sqlalchemy as sa

revision = "20260908_0009"
down_revision = "20260908_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_daily_price_bars",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("instrument_id", sa.String(100), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(), nullable=False),
        sa.Column("high", sa.Numeric(), nullable=False),
        sa.Column("low", sa.Numeric(), nullable=False),
        sa.Column("close", sa.Numeric(), nullable=False),
        sa.Column("previous_close", sa.Numeric(), nullable=True),
        sa.Column("session_opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("source_feed", sa.String(50), nullable=False),
        sa.Column("quality", sa.String(40), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("adjustment", sa.String(20), nullable=False),
        sa.Column("price_scope", sa.String(60), nullable=False),
        sa.UniqueConstraint("instrument_id", "trading_date"),
        sa.CheckConstraint('"low" > 0 AND "high" < 10000000000000000'),
        sa.CheckConstraint(
            '"low" <= "open" AND "low" <= "close" AND "high" >= "open" AND "high" >= "close"'
        ),
        sa.CheckConstraint(
            "previous_close IS NULL OR (previous_close > 0 AND previous_close < 10000000000000000)"
        ),
        sa.CheckConstraint(
            "market_timestamp <= session_opened_at AND session_opened_at < session_closed_at AND session_closed_at <= observed_at"
        ),
        sa.CheckConstraint("currency = 'USD' AND adjustment = 'raw'"),
        sa.CheckConstraint("quality IN ('REALTIME', 'DELAYED', 'MOCK')"),
        sa.CheckConstraint("price_scope = 'CONSOLIDATED_DAILY_ELIGIBLE_TRADES'"),
    )
    for column in ("instrument_id", "trading_date"):
        op.create_index(f"ix_market_daily_price_bars_{column}", "market_daily_price_bars", [column])
    op.execute("""
        CREATE FUNCTION reject_daily_price_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'Daily price history is immutable; corrections require reviewed revisions';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute(
        "CREATE TRIGGER immutable_market_daily_price_bars "
        "BEFORE UPDATE OR DELETE ON market_daily_price_bars FOR EACH ROW "
        "EXECUTE FUNCTION reject_daily_price_mutation()"
    )


def downgrade() -> None:
    op.drop_table("market_daily_price_bars")
    op.execute("DROP FUNCTION reject_daily_price_mutation()")
