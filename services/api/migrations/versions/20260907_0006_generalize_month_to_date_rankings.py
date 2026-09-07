"""generalize month-to-date ranking status

Revision ID: 20260907_0006
Revises: 20260907_0005
Create Date: 2026-09-07
"""

from typing import Optional, Sequence, Union

from alembic import op

revision: str = "20260907_0006"
down_revision: Optional[str] = "20260907_0005"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_market_ranking_period_status",
        "market_rankings",
        type_="check",
    )
    op.create_check_constraint(
        "ck_market_ranking_period_status",
        "market_rankings",
        "period_status IN ('SEPTEMBER_TO_DATE', 'MONTH_TO_DATE', 'FINAL')",
    )


def downgrade() -> None:
    # Ranking datasets are provider-reproducible; discard statuses the older
    # schema cannot represent instead of silently relabeling their provenance.
    op.execute("DELETE FROM market_rankings WHERE period_status = 'MONTH_TO_DATE'")
    op.drop_constraint(
        "ck_market_ranking_period_status",
        "market_rankings",
        type_="check",
    )
    op.create_check_constraint(
        "ck_market_ranking_period_status",
        "market_rankings",
        "period_status IN ('SEPTEMBER_TO_DATE', 'FINAL')",
    )
