"""Provenance, assumptions, approvals, and traceable RBI events."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class DataQualityStatus(Base):
    __tablename__ = "data_quality_status"
    __table_args__ = (
        CheckConstraint(
            "quality IN ('unverified', 'verified', 'assumed', 'defaulted')",
            name="ck_data_quality_status_quality",
        ),
        Index(
            "ix_data_quality_entity_field",
            "entity_type",
            "entity_id",
            "field_name",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    field_name: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(120))
    source_date: Mapped[datetime] = mapped_column(DateTime)
    recorded_by: Mapped[str] = mapped_column(String(80))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    quality: Mapped[str] = mapped_column(String(20), default="unverified")
    note: Mapped[str] = mapped_column(Text, default="")


class EngineeringAssumption(Base):
    __tablename__ = "engineering_assumption"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    field_name: Mapped[str] = mapped_column(String(80))
    assumed_value: Mapped[str] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ApprovalWorkflow(Base):
    __tablename__ = "approval_workflow"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('pending', 'reviewed', 'approved', 'rejected')",
            name="ck_approval_workflow_stage",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(30), default="pending")
    requested_by: Mapped[str] = mapped_column(String(80))
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")


class TraceableEvent(Base):
    __tablename__ = "traceable_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actor: Mapped[str] = mapped_column(String(80))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
