"""Allow provider-reported Futu Profit Ratio observations alongside model data.

Revision ID: 20260912_0010
Revises: 20260908_0009
"""

from alembic import op
import sqlalchemy as sa

revision = "20260912_0010"
down_revision = "20260908_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profit_ratio_capture_prices",
        sa.Column(
            "methodology_key",
            sa.String(100),
            nullable=False,
            server_default="CHIP_TURNOVER",
        ),
    )
    op.add_column(
        "profit_ratio_capture_prices",
        sa.Column(
            "methodology_version",
            sa.String(20),
            nullable=False,
            server_default="1",
        ),
    )
    op.alter_column("profit_ratio_capture_prices", "methodology_key", server_default=None)
    op.alter_column("profit_ratio_capture_prices", "methodology_version", server_default=None)
    op.drop_constraint(
        "profit_ratio_capture_prices_instrument_id_trading_date_phas_key",
        "profit_ratio_capture_prices",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_profit_ratio_price_methodology",
        "profit_ratio_capture_prices",
        [
            "instrument_id",
            "trading_date",
            "phase",
            "methodology_key",
            "methodology_version",
        ],
    )
    op.drop_constraint(
        "profit_ratio_observations_check",
        "profit_ratio_observations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_profit_ratio_observation_status",
        "profit_ratio_observations",
        "(status = 'DATA_INSUFFICIENT' AND ratio IS NULL) OR "
        "(status IN ('ESTIMATED', 'REPORTED') AND ratio IS NOT NULL)",
    )


def downgrade() -> None:
    # Revision 0009 did not know the provenance distinction between reported and
    # calculated ratios. Preserve the value/methodology while mapping its status
    # to the only non-null state understood by that older schema.
    op.execute("DROP TRIGGER immutable_profit_ratio_observations ON profit_ratio_observations")
    op.execute("UPDATE profit_ratio_observations SET status = 'ESTIMATED' WHERE status = 'REPORTED'")
    op.execute(
        "CREATE TRIGGER immutable_profit_ratio_observations "
        "BEFORE UPDATE OR DELETE ON profit_ratio_observations FOR EACH ROW "
        "EXECUTE FUNCTION reject_profit_ratio_mutation()"
    )
    op.drop_constraint(
        "ck_profit_ratio_observation_status",
        "profit_ratio_observations",
        type_="check",
    )
    op.create_check_constraint(
        "profit_ratio_observations_check",
        "profit_ratio_observations",
        "(status = 'DATA_INSUFFICIENT' AND ratio IS NULL) OR "
        "(status = 'ESTIMATED' AND ratio IS NOT NULL)",
    )
    op.drop_constraint(
        "uq_profit_ratio_price_methodology",
        "profit_ratio_capture_prices",
        type_="unique",
    )
    op.create_unique_constraint(
        "profit_ratio_capture_prices_instrument_id_trading_date_phas_key",
        "profit_ratio_capture_prices",
        ["instrument_id", "trading_date", "phase"],
    )
    op.drop_column("profit_ratio_capture_prices", "methodology_version")
    op.drop_column("profit_ratio_capture_prices", "methodology_key")
