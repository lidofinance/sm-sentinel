"""Shared SQLite schema. Runtime and domain objects are not ORM entities."""

from sqlalchemy import CheckConstraint, Float, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RuntimeIdentityRow(Base):
    __tablename__ = "runtime_identity"
    __table_args__ = (CheckConstraint("id = 1", name="runtime_identity_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[str]
    module_address: Mapped[str]
    module_type: Mapped[str]


class ChatMigrationRow(Base):
    __tablename__ = "chat_migrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    old_chat_id: Mapped[int] = mapped_column(unique=True)
    new_chat_id: Mapped[int]


class AlertmanagerRequestRow(Base):
    __tablename__ = "alertmanager_requests"

    source_id: Mapped[str] = mapped_column(primary_key=True)
    digest: Mapped[str] = mapped_column(primary_key=True)
    expires_at: Mapped[float] = mapped_column(Float)


class AlertmanagerDeliveryRow(Base):
    __tablename__ = "alertmanager_deliveries"
    __table_args__ = (
        Index("alertmanager_deliveries_request", "source_id", "request_digest"),
        Index("alertmanager_deliveries_source", "source_id", "id"),
        Index("alertmanager_deliveries_chat", "chat_id", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str]
    request_digest: Mapped[str]
    node_operator_id: Mapped[str]
    chat_id: Mapped[int]
    message: Mapped[str]
    enqueued_at: Mapped[float] = mapped_column(Float)
