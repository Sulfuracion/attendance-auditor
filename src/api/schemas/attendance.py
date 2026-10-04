"""Pydantic v2 schemas for attendance ingestion, records, and incident resolution."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.db.models.enums import FileStatus, IncidentStatus


class IncidentResponse(BaseModel):
    """Incident audit and review details."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    reason: str
    status: IncidentStatus
    supervisor_id: UUID | None = None
    reviewed_at: datetime | None = None


class IncidentJustifyRequest(BaseModel):
    """Payload to review and justify an attendance incident."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Justification note or supervisor explanation",
    )
    status: IncidentStatus = Field(
        default=IncidentStatus.APPROVED,
        description="Updated incident state (APPROVED or REJECTED)",
    )


class AttendanceRecordResponse(BaseModel):
    """Detailed attendance day record DTO."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    employee_code: str
    date: date
    punch_in: datetime | None = None
    punch_out: datetime | None = None
    ordinary_hours: float
    night_hours: float
    holiday_hours: float
    excess_hours: float
    has_incident: bool
    incidents: list[IncidentResponse] = Field(default_factory=list)


class AttendanceSummaryItem(BaseModel):
    """Per-employee aggregated labor hours metric."""

    model_config = ConfigDict(extra="forbid")

    employee_code: str
    total_hours: float
    ordinary_hours: float
    night_hours: float
    holiday_hours: float
    excess_hours: float
    incidents_count: int


class AttendanceSummaryResponse(BaseModel):
    """High-level analytical summary for an organization tenant."""

    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    total_records: int
    total_hours: float
    total_incidents: int
    items: list[AttendanceSummaryItem]


class UploadResponse(BaseModel):
    """Ingestion feedback payload."""

    model_config = ConfigDict(extra="forbid")

    file_id: UUID
    filename: str
    total_rows_processed: int
    reconciled_shifts: int
    incidents_detected: int
    status: FileStatus


class PunchActionRequest(BaseModel):
    """Payload to register an interactive punch event (IN or OUT)."""

    model_config = ConfigDict(extra="forbid")

    action: IncidentStatus | str = Field(
        ...,
        description="Punch direction: 'IN' (Entrada) or 'OUT' (Salida)",
    )
    timestamp: datetime | None = Field(
        default=None,
        description="Optional custom timestamp; defaults to server UTC now",
    )


class PunchStatusResponse(BaseModel):
    """Real-time active shift state for the current worker."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="'IN_PROGRESS' or 'IDLE'")
    active_record: AttendanceRecordResponse | None = None
    last_punch: datetime | None = None


class AttendanceRecordUpdateRequest(BaseModel):
    """Payload for supervisors/admins to rectify attendance punch times."""

    model_config = ConfigDict(extra="forbid")

    punch_in: datetime = Field(..., description="Corrected punch in timestamp")
    punch_out: datetime = Field(..., description="Corrected punch out timestamp")
    reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Audit note detailing the supervisor's rectification rationale",
    )


class BulkChangeItem(BaseModel):
    """Detected single attendance modification between uploaded spreadsheet and existing records."""

    model_config = ConfigDict(extra="forbid")

    change_type: str = Field(..., description="'MODIFIED', 'NEW', or 'UNCHANGED'")
    record_id: UUID | None = Field(default=None, description="Existing record ID if updating")
    employee_code: str
    employee_name: str | None = None
    date: date
    old_punch_in: datetime | None = None
    old_punch_out: datetime | None = None
    old_ordinary_hours: float = 0.0
    old_excess_hours: float = 0.0
    new_punch_in: datetime
    new_punch_out: datetime
    new_ordinary_hours: float
    new_excess_hours: float


class BulkDiffPreviewResponse(BaseModel):
    """Detailed diff comparison feedback before applying batch Excel changes."""

    model_config = ConfigDict(extra="forbid")

    total_rows_inspected: int
    changes_count: int
    new_records_count: int
    modified_records_count: int
    unchanged_count: int
    changes: list[BulkChangeItem]


class BulkApplyChangesRequest(BaseModel):
    """Confirmation payload to persist previewed modifications."""

    model_config = ConfigDict(extra="forbid")

    changes: list[BulkChangeItem]
    audit_reason: str = Field(
        default="Actualización masiva desde Excel",
        max_length=500,
        description="Justification note for bulk changes",
    )

