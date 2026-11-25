"""Store per-user Alertmanager source opt-outs.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alertmanager_disabled_sources",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(), primary_key=True),
    )
    op.create_index(
        "alertmanager_disabled_sources_source",
        "alertmanager_disabled_sources",
        ["source_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_table("alertmanager_disabled_sources")
