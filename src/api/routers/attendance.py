"""Attendance, Ingestion, Incident Resolution, and Export endpoints."""

from datetime import date
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, require_roles
from src.api.schemas.attendance import (
    AttendanceRecordResponse,
    AttendanceRecordUpdateRequest,
    AttendanceSummaryResponse,
    BulkApplyChangesRequest,
    BulkDiffPreviewResponse,
    IncidentJustifyRequest,
    IncidentResponse,
    PunchActionRequest,
    PunchStatusResponse,
    UploadResponse,
)
from src.api.schemas.auth import AuthenticatedUser
from src.core.parsers.normalizer import ParserError
from src.core.parsers.validator import FileValidationError
from src.db.models.enums import UserRole
from src.db.session import get_db_session
from src.services.attendance_service import AttendanceService
from src.services.auth_service import AuthorizationError, ResourceNotFoundError

router = APIRouter(prefix="/attendance", tags=["Attendance & Auditing"])

# Default uploads directory
DEFAULT_STORAGE_ROOT = Path("storage/uploads")


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and reconcile biometric/attendance file",
)
async def upload_attendance_file(
    file: Annotated[UploadFile, File(description="CSV or Excel attendance log file")],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(UserRole.ADMIN, UserRole.SUPERVISOR)),
    ],
) -> UploadResponse:
    """Ingest, validate, normalize, and reconcile attendance events into tenant records."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename",
        )

    try:
        response = await AttendanceService.process_uploaded_file(
            session=session,
            current_user=current_user,
            stream=file.file,
            original_filename=file.filename,
            storage_directory=DEFAULT_STORAGE_ROOT,
        )
        return response
    except FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File validation failed: {e}",
        ) from e
    except ParserError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Parsing error: {e}",
        ) from e


@router.post(
    "/preview-changes",
    response_model=BulkDiffPreviewResponse,
    summary="Inspect and diff an Excel spreadsheet against current records without applying",
)
async def preview_excel_modifications(
    file: Annotated[UploadFile, File(description="Excel or CSV modified attendance file")],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(UserRole.ADMIN, UserRole.SUPERVISOR)),
    ],
) -> BulkDiffPreviewResponse:
    """Compare uploaded file with existing records to detect modifications and new records."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe tener un nombre válido",
        )

    try:
        return await AttendanceService.preview_excel_modifications(
            session=session,
            current_user=current_user,
            stream=file.file,
            original_filename=file.filename,
        )
    except FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error en validación de archivo: {e}",
        ) from e
    except ParserError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error de formato al procesar datos: {e}",
        ) from e


@router.post(
    "/apply-changes",
    response_model=dict[str, int],
    summary="Apply confirmed bulk modifications to attendance records",
)
async def apply_bulk_modifications(
    payload: BulkApplyChangesRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(UserRole.ADMIN, UserRole.SUPERVISOR)),
    ],
) -> dict[str, int]:
    """Persist confirmed batch changes from user confirmation dialog."""
    try:
        count = await AttendanceService.apply_bulk_changes(
            session=session,
            current_user=current_user,
            payload=payload,
        )
        return {"applied_count": count}
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e



@router.get(
    "/records",
    response_model=list[AttendanceRecordResponse],
    summary="List reconciled attendance records",
)
async def get_records(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    employee_code: Annotated[str | None, Query(description="Filter by employee code")] = None,
    date_from: Annotated[date | None, Query(description="Filter from date (inclusive)")] = None,
    date_to: Annotated[date | None, Query(description="Filter to date (inclusive)")] = None,
    only_incidents: Annotated[bool, Query(description="Show only records with incidents")] = False,
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=500, description="Records limit")] = 100,
) -> list[AttendanceRecordResponse]:
    """Retrieve itemized attendance records scoped strictly to user's tenant organization."""
    return await AttendanceService.get_attendance_records(
        session=session,
        current_user=current_user,
        employee_code=employee_code,
        date_from=date_from,
        date_to=date_to,
        only_incidents=only_incidents,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/summary",
    response_model=AttendanceSummaryResponse,
    summary="Get aggregated attendance analytics summary",
)
async def get_summary(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    employee_code: Annotated[str | None, Query(description="Filter by employee code")] = None,
    date_from: Annotated[date | None, Query(description="Start date")] = None,
    date_to: Annotated[date | None, Query(description="End date")] = None,
) -> AttendanceSummaryResponse:
    """Retrieve aggregate labor hours and incident statistics."""
    return await AttendanceService.get_attendance_summary(
        session=session,
        current_user=current_user,
        employee_code=employee_code,
        date_from=date_from,
        date_to=date_to,
    )


@router.post(
    "/incidents/{record_id}/justify",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Review and justify an attendance incident",
)
async def justify_incident(
    record_id: UUID,
    data: IncidentJustifyRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(UserRole.ADMIN, UserRole.SUPERVISOR)),
    ],
) -> IncidentResponse:
    """Resolve an attendance incident (Supervisors and Admins only)."""
    try:
        return await AttendanceService.justify_incident(
            session=session,
            current_user=current_user,
            record_id=record_id,
            data=data,
        )
    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


@router.get(
    "/export",
    summary="Download secured multi-sheet Excel audit report",
)
async def export_excel_report(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    employee_code: Annotated[str | None, Query(description="Filter by employee code")] = None,
    date_from: Annotated[date | None, Query(description="Start date")] = None,
    date_to: Annotated[date | None, Query(description="End date")] = None,
) -> StreamingResponse:
    """Export attendance audit report into a formatted, secure Excel (.xlsx) workbook."""
    stream = await AttendanceService.generate_attendance_report(
        session=session,
        current_user=current_user,
        employee_code=employee_code,
        date_from=date_from,
        date_to=date_to,
    )

    headers = {
        "Content-Disposition": 'attachment; filename="reporte_asistencia.xlsx"',
        "X-Content-Type-Options": "nosniff",
    }

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get(
    "/template",
    summary="Download Excel template for bulk biometric punches import",
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.SUPERVISOR))],
)
async def download_biometric_template() -> StreamingResponse:
    """Download standard biometric punch import Excel (.xlsx) template.

    Restricted to ADMIN and SUPERVISOR roles.
    """
    stream = AttendanceService.get_biometric_template()

    headers = {
        "Content-Disposition": 'attachment; filename="plantilla_fichajes_biometricos.xlsx"',
        "X-Content-Type-Options": "nosniff",
    }

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get(
    "/punch/status",
    response_model=PunchStatusResponse,
    summary="Get active punch shift status for current user",
)
async def get_punch_status(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> PunchStatusResponse:
    """Check if the user is currently clocked in (IN_PROGRESS) or clocked out (IDLE)."""
    return await AttendanceService.get_punch_status(session, current_user)


@router.post(
    "/punch",
    response_model=AttendanceRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record live worker attendance punch (IN or OUT)",
)
async def record_live_punch(
    data: PunchActionRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AttendanceRecordResponse:
    """Record an immutable worker attendance event.

    Workers cannot edit or delete their punches once recorded.
    """
    try:
        return await AttendanceService.record_live_punch(
            session=session,
            current_user=current_user,
            data=data,
        )
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e


@router.put(
    "/records/{record_id}",
    response_model=AttendanceRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Supervisor/Admin manual rectification of attendance punch hours",
)
async def update_attendance_record(
    record_id: UUID,
    data: AttendanceRecordUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(UserRole.ADMIN, UserRole.SUPERVISOR)),
    ],
) -> AttendanceRecordResponse:
    """Allow supervisors and admins to rectify punch times with automatic recalculation."""
    try:
        return await AttendanceService.update_attendance_record(
            session=session,
            current_user=current_user,
            record_id=record_id,
            data=data,
        )
    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
