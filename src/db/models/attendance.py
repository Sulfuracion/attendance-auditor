"""Attendance and Incident ORM models for ingestion and reconciliation."""

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.enums import FileStatus, IncidentStatus
from src.db.session import Base

if TYPE_CHECKING:
    from src.db.models.employee import Employee
    from src.db.models.organization import Organization
    from src.db.models.user import User


class AttendanceFile(Base):
    """File ingestion audit log and processing lifecycle tracking."""

    __tablename__ = "attendance_files"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    status: Mapped[FileStatus] = mapped_column(
        Enum(FileStatus, name="file_status_enum", native_enum=False),
        nullable=False,
        default=FileStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="attendance_files"
    )
    uploaded_by_user: Mapped["User"] = relationship("User", back_populates="uploaded_files")
    records: Mapped[list["AttendanceRecord"]] = relationship(
        "AttendanceRecord", back_populates="file", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_attendance_files_org_id", "organization_id"),
        Index("ix_attendance_files_status", "status"),
        Index("ix_attendance_files_created_at", "created_at"),
    )


class AttendanceRecord(Base):
    """Reconciled attendance day record with computed vectorized labor hours."""

    __tablename__ = "attendance_records"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("attendance_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    punch_in: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    punch_out: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ordinary_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    night_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    holiday_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    excess_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    has_incident: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendance_records")
    file: Mapped["AttendanceFile | None"] = relationship("AttendanceFile", back_populates="records")
    incidents: Mapped[list["Incident"]] = relationship(
        "Incident", back_populates="attendance_record", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_attendance_records_emp_date", "employee_id", "date"),
        Index("ix_attendance_records_file_id", "file_id"),
        Index("ix_attendance_records_has_incident", "has_incident"),
    )


class Incident(Base):
    """Attendance incident justification, anomaly, or supervisor rectification."""

    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    attendance_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("attendance_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    supervisor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status_enum", native_enum=False),
        nullable=False,
        default=IncidentStatus.PENDING,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    attendance_record: Mapped["AttendanceRecord"] = relationship(
        "AttendanceRecord", back_populates="incidents"
    )
    supervisor: Mapped["User | None"] = relationship("User", back_populates="reviewed_incidents")

    __table_args__ = (
        Index("ix_incidents_record_id", "attendance_record_id"),
        Index("ix_incidents_supervisor_id", "supervisor_id"),
        Index("ix_incidents_status", "status"),
    )
