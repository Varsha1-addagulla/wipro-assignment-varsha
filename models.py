"""SQLAlchemy ORM models.

The ``ApiLog`` table audits every call that reaches ``/assess``: applicant
context (name only — no other PII is stored), final decision, latency, and
any error text. ``CreatedAt``/``UpdatedAt``/``CreatedBy``/``UpdatedBy`` are
maintained on every row per project convention.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApiLog(Base):
    """Audit record for every API call handled by the service."""

    __tablename__ = "api_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    endpoint: Mapped[str] = mapped_column(String(128))
    http_method: Mapped[str] = mapped_column(String(8))
    status_code: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    applicant_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    average_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_summary: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )

    # Audit columns — populated on every write.
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    UpdatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )
    CreatedBy: Mapped[str] = mapped_column(String(128), default="system")
    UpdatedBy: Mapped[str] = mapped_column(String(128), default="system")
