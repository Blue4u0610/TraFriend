"""add ranking asset metadata and completeness

Revision ID: 20260906_0003
Revises: 20260906_0002
Create Date: 2026-09-06
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_0003"
down_revision: Optional[str] = "20260906_0002"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        "market_rankings",
        sa.Column("display_name", sa.String(length=256), server_default="", nullable=False),
    )
    op.add_column(
        "market_rankings",
        sa.Column("exchange", sa.String(length=8), server_default="", nullable=False),
    )
    op.add_column(
        "market_rankings",
        sa.Column(
            "completeness_status",
            sa.String(length=16),
            server_default="COMPLETE",
            nullable=False,
        ),
    )
    op.add_column(
        "market_rankings",
        sa.Column("sessions_observed", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "market_rankings",
        sa.Column("sessions_expected", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_market_ranking_completeness_status",
        "market_rankings",
        "completeness_status IN ('COMPLETE', 'INCOMPLETE')",
    )
    op.create_check_constraint(
        "ck_market_ranking_session_counts",
        "market_rankings",
        "sessions_observed >= 0 AND sessions_expected >= 0 "
        "AND sessions_observed <= sessions_expected",
    )
    for column in (
        "display_name",
        "exchange",
        "completeness_status",
        "sessions_observed",
        "sessions_expected",
    ):
        op.alter_column("market_rankings", column, server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_market_ranking_session_counts", "market_rankings", type_="check"
    )
    op.drop_constraint(
        "ck_market_ranking_completeness_status", "market_rankings", type_="check"
    )
    op.drop_column("market_rankings", "sessions_expected")
    op.drop_column("market_rankings", "sessions_observed")
    op.drop_column("market_rankings", "completeness_status")
    op.drop_column("market_rankings", "exchange")
    op.drop_column("market_rankings", "display_name")
