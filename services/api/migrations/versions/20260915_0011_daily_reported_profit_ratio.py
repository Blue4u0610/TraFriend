"""Store one immutable provider-reported Profit Ratio value per trading day.

Revision ID: 20260915_0011
Revises: 20260912_0010
"""

from alembic import op
import sqlalchemy as sa

revision = "20260915_0011"
down_revision = "20260912_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profit_ratio_daily_observations",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("instrument_id", sa.String(100), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("ratio", sa.Numeric(), nullable=False),
        sa.Column("time_basis", sa.String(40), nullable=False),
        sa.Column("market_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("source_feed", sa.String(100), nullable=False),
        sa.Column("quality", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("methodology_key", sa.String(100), nullable=False),
        sa.Column("methodology_version", sa.String(20), nullable=False),
        sa.Column("source_note", sa.String(500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "instrument_id",
            "trading_date",
            "methodology_key",
            "methodology_version",
            "time_basis",
            "version",
            name="uq_profit_ratio_daily_observation_version",
        ),
        sa.CheckConstraint("ratio >= 0 AND ratio <= 1"),
        sa.CheckConstraint(
            "time_basis IN ('CLOSE', 'DAILY_TIME_UNVERIFIED')",
            name="ck_profit_ratio_daily_time_basis",
        ),
        sa.CheckConstraint(
            "(time_basis = 'CLOSE' AND market_timestamp IS NOT NULL) OR "
            "(time_basis = 'DAILY_TIME_UNVERIFIED' AND market_timestamp IS NULL)",
            name="ck_profit_ratio_daily_market_timestamp",
        ),
        sa.CheckConstraint("status = 'REPORTED'"),
        sa.CheckConstraint("version > 0"),
        sa.CheckConstraint("market_timestamp IS NULL OR market_timestamp <= observed_at"),
    )
    op.create_index(
        "ix_profit_ratio_daily_observations_instrument_id",
        "profit_ratio_daily_observations",
        ["instrument_id"],
    )
    op.create_index(
        "ix_profit_ratio_daily_observations_trading_date",
        "profit_ratio_daily_observations",
        ["trading_date"],
    )
    op.execute("""
        CREATE FUNCTION reject_profit_ratio_daily_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'Daily Profit Ratio history is immutable; corrections require a new version';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute(
        "CREATE TRIGGER immutable_profit_ratio_daily_observations "
        "BEFORE UPDATE OR DELETE ON profit_ratio_daily_observations FOR EACH ROW "
        "EXECUTE FUNCTION reject_profit_ratio_daily_mutation()"
    )


def downgrade() -> None:
    op.drop_table("profit_ratio_daily_observations")
    op.execute("DROP FUNCTION reject_profit_ratio_daily_mutation()")
