"""Create the shared Sentinel database.

Revision ID: 0001
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_identity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain_id", sa.String(), nullable=False),
        sa.Column("module_address", sa.String(), nullable=False),
        sa.Column("module_type", sa.String(), nullable=False),
        sa.CheckConstraint("id = 1", name="runtime_identity_singleton"),
    )
    op.create_table(
        "chat_migrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("old_chat_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("new_chat_id", sa.Integer(), nullable=False),
    )
    op.create_table(
        "alertmanager_requests",
        sa.Column("source_id", sa.String(), primary_key=True),
        sa.Column("digest", sa.String(), primary_key=True),
        sa.Column("expires_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "alertmanager_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("request_digest", sa.String(), nullable=False),
        sa.Column("node_operator_id", sa.String(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("enqueued_at", sa.Float(), nullable=False),
    )
    op.create_index(
        "alertmanager_deliveries_request",
        "alertmanager_deliveries",
        ["source_id", "request_digest"],
    )
    op.create_index(
        "alertmanager_deliveries_source",
        "alertmanager_deliveries",
        ["source_id", "id"],
    )
    op.create_index("alertmanager_deliveries_chat", "alertmanager_deliveries", ["chat_id", "id"])


def downgrade() -> None:
    op.drop_table("alertmanager_deliveries")
    op.drop_table("alertmanager_requests")
    op.drop_table("chat_migrations")
    op.drop_table("runtime_identity")
