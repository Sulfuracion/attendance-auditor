"""Attendance service layer for file ingestion, query filtering, and incident management.

Guarantees:
- Strict multi-tenant isolation (IDOR/BOLA mitigation) across all operations.
- Vectorized processing via parsers and reconciliation engines.
- Atomic database persistence with SQLAlchemy 2.0 async sessions.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import openpyxl
import pandas as pd
from sqlalchemy import ColumnElement, case, false, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas.attendance import (
    AttendanceRecordResponse,
    AttendanceRecordUpdateRequest,
    AttendanceSummaryItem,
    AttendanceSummaryResponse,
    BulkApplyChangesRequest,
    BulkChangeItem,
    BulkDiffPreviewResponse,
    IncidentJustifyRequest,
    IncidentResponse,
    PunchActionRequest,
    PunchStatusResponse,
    UploadResponse,
)
from src.api.schemas.auth import AuthenticatedUser
from src.core.exporters.excel import (
    export_attendance_to_excel,
    generate_biometric_template,
)
from src.core.parsers.normalizer import normalize_attendance_file
from src.core.parsers.validator import (
    inspect_and_validate_stream,
    sanitize_and_resolve_storage_path,
)
from src.core.reconciliation.engine import reconcile_attendance_events
from src.core.rules.shifts import (
    compute_holiday_hours_vectorized,
    compute_labor_distribution_vectorized,
    compute_night_hours_vectorized,
)
from src.db.models.attendance import AttendanceFile, AttendanceRecord, Incident
from src.db.models.employee import Employee
from src.db.models.enums import FileStatus, IncidentStatus, UserRole
from src.db.models.holiday import Holiday
from src.db.models.user import User
from src.services.auth_service import AuthorizationError, ResourceNotFoundError


class AttendanceService:
    """Service handling attendance domain operations and reports."""

    @staticmethod
    async def _worker_scope_condition(
        session: AsyncSession,
        current_user: AuthenticatedUser,
    ) -> ColumnElement[bool] | None:
        """Build the WHERE condition restricting WORKER queries to their own Employee.

        BOLA mitigation: workers can never widen the scope via query parameters, since
        the filter derives server-side from the persisted user->employee link.
        Workers without a linked employee get an always-false condition (empty result).
        Returns None for roles with organization-wide visibility.
        """
        if current_user.role != UserRole.WORKER:
            return None

        link_stmt = select(User.employee_id).where(
            User.id == current_user.id,
            User.organization_id == current_user.organization_id,
        )
        employee_id = (await session.execute(link_stmt)).scalar_one_or_none()
        if employee_id is None:
            return false()
        return Employee.id == employee_id

    @staticmethod
    async def process_uploaded_file(
        session: AsyncSession,
        current_user: AuthenticatedUser,
        stream: BinaryIO | BytesIO,
        original_filename: str,
        storage_directory: Path,
    ) -> UploadResponse:
        """Validate, store, normalize, reconcile, and persist attendance events.

        Args:
            session: Transactional async database session.
            current_user: Authenticated tenant user.
            stream: Open binary file stream.
            original_filename: Non-trusted filename supplied by user.
            storage_directory: Base server directory for persisting files.

        Returns:
            UploadResponse with processing statistics.
        """
        # 1. Inspect stream, check size limit and verify true magic bytes
        file_format, _total_size = inspect_and_validate_stream(stream, original_filename)

        # 2. Mitigate Path Traversal by resolving canonical storage path
        saved_path = sanitize_and_resolve_storage_path(
            storage_directory, original_filename, file_format
        )

        # 3. Persist file safely to disk
        stream.seek(0)
        file_bytes = stream.read()
        saved_path.write_bytes(file_bytes)
        stream.seek(0)

        # 4. Create initial DB audit record
        attendance_file = AttendanceFile(
            organization_id=current_user.organization_id,
            uploaded_by_user_id=current_user.id,
            filename=original_filename[:255],
            storage_path=str(saved_path),
            status=FileStatus.PENDING,
        )
        session.add(attendance_file)
        await session.flush()

        # 5. Normalize into canonical DataFrame
        canonical_df = normalize_attendance_file(BytesIO(file_bytes), file_format)

        # 6. Retrieve organization holiday dates
        holidays_stmt = select(Holiday.date).where(
            Holiday.organization_id == current_user.organization_id
        )
        holidays_res = await session.execute(holidays_stmt)
        holiday_dates: list[date] = list(holidays_res.scalars().all())

        # 7. Execute vectorized reconciliation engine
        reconciled_df = reconcile_attendance_events(canonical_df, holiday_dates=holiday_dates)

        # 8. Ensure all referenced employees exist for this tenant
        unique_emp_codes: Sequence[str] = reconciled_df["employee_code"].unique().tolist()
        existing_emp_stmt = select(Employee).where(
            Employee.organization_id == current_user.organization_id,
            Employee.employee_code.in_(unique_emp_codes),
        )
        existing_res = await session.execute(existing_emp_stmt)
        existing_emps = {e.employee_code: e for e in existing_res.scalars().all()}

        # Auto-provision missing employee records with default contract hours
        for emp_code in unique_emp_codes:
            if emp_code not in existing_emps:
                new_emp = Employee(
                    organization_id=current_user.organization_id,
                    employee_code=emp_code,
                    first_name="Empleado",
                    last_name=emp_code,
                    weekly_contract_hours=40.0,
                )
                session.add(new_emp)
                await session.flush()
                existing_emps[emp_code] = new_emp

        # 9. Persist AttendanceRecord entries (vectorized column prep + ORM bulk INSERT)
        emp_id_map: dict[str, UUID] = {code: emp.id for code, emp in existing_emps.items()}
        punch_in_s = reconciled_df["punch_in"]
        punch_out_s = reconciled_df["punch_out"]
        persist_df = pd.DataFrame(
            {
                "employee_id": reconciled_df["employee_code"].map(emp_id_map),
                "file_id": attendance_file.id,
                "date": reconciled_df["date"],
                # Orphan punches: column is NOT NULL, so mirror the existing counterpart.
                # The record keeps has_incident=True for supervisor review.
                "punch_in": punch_in_s.fillna(punch_out_s),
                "punch_out": punch_out_s.fillna(punch_in_s),
                "ordinary_hours": reconciled_df["ordinary_hours"].astype("float64"),
                "night_hours": reconciled_df["night_hours"].astype("float64"),
                "holiday_hours": reconciled_df["holiday_hours"].astype("float64"),
                "excess_hours": reconciled_df["excess_hours"].astype("float64"),
                "has_incident": reconciled_df["has_incident"].astype(bool),
            }
        )
        persist_df = persist_df.dropna(subset=["punch_in", "punch_out", "employee_id"])

        if not persist_df.empty:
            # pd.Timestamp subclasses datetime, so DB drivers bind it natively.
            await session.execute(
                insert(AttendanceRecord),
                persist_df.to_dict(orient="records"),
            )

        attendance_file.status = FileStatus.PROCESSED
        await session.flush()

        reconciled_shifts = int((~reconciled_df["has_incident"]).sum())
        incidents_detected = int(reconciled_df["has_incident"].sum())

        return UploadResponse(
            file_id=attendance_file.id,
            filename=attendance_file.filename,
            total_rows_processed=len(canonical_df),
            reconciled_shifts=reconciled_shifts,
            incidents_detected=incidents_detected,
            status=attendance_file.status,
        )

    @staticmethod
    async def get_attendance_records(
        session: AsyncSession,
        current_user: AuthenticatedUser,
        employee_code: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        only_incidents: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AttendanceRecordResponse]:
        """Query paginated attendance records scoped to tenant."""
        stmt = (
            select(AttendanceRecord, Employee.employee_code)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .options(selectinload(AttendanceRecord.incidents))
            .where(Employee.organization_id == current_user.organization_id)
        )
        scope = await AttendanceService._worker_scope_condition(session, current_user)
        if scope is not None:
            stmt = stmt.where(scope)

        if employee_code:
            stmt = stmt.where(Employee.employee_code == employee_code)
        if date_from:
            stmt = stmt.where(AttendanceRecord.date >= date_from)
        if date_to:
            stmt = stmt.where(AttendanceRecord.date <= date_to)
        if only_incidents:
            stmt = stmt.where(AttendanceRecord.has_incident.is_(True))

        stmt = stmt.order_by(AttendanceRecord.date.desc()).offset(skip).limit(min(limit, 500))
        res = await session.execute(stmt)
        results = res.all()

        responses: list[AttendanceRecordResponse] = []
        for record, emp_code in results:
            inc_responses = [
                IncidentResponse(
                    id=inc.id,
                    reason=inc.reason,
                    status=inc.status,
                    supervisor_id=inc.supervisor_id,
                    reviewed_at=inc.reviewed_at,
                )
                for inc in record.incidents
            ]
            responses.append(
                AttendanceRecordResponse(
                    id=record.id,
                    employee_code=emp_code,
                    date=record.date,
                    punch_in=record.punch_in,
                    punch_out=record.punch_out,
                    ordinary_hours=record.ordinary_hours,
                    night_hours=record.night_hours,
                    holiday_hours=record.holiday_hours,
                    excess_hours=record.excess_hours,
                    has_incident=record.has_incident,
                    incidents=inc_responses,
                )
            )

        return responses

    @staticmethod
    async def get_attendance_summary(
        session: AsyncSession,
        current_user: AuthenticatedUser,
        employee_code: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> AttendanceSummaryResponse:
        """Calculate aggregated metrics per employee for the current tenant."""
        stmt = (
            select(
                Employee.employee_code,
                func.sum(AttendanceRecord.ordinary_hours + AttendanceRecord.excess_hours).label(
                    "total_hours"
                ),
                func.sum(AttendanceRecord.ordinary_hours).label("ordinary_hours"),
                func.sum(AttendanceRecord.night_hours).label("night_hours"),
                func.sum(AttendanceRecord.holiday_hours).label("holiday_hours"),
                func.sum(AttendanceRecord.excess_hours).label("excess_hours"),
                func.count(AttendanceRecord.id).label("total_records"),
                func.sum(case((AttendanceRecord.has_incident.is_(True), 1), else_=0)).label(
                    "incidents_count"
                ),
            )
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(Employee.organization_id == current_user.organization_id)
            .group_by(Employee.employee_code)
        )
        scope = await AttendanceService._worker_scope_condition(session, current_user)
        if scope is not None:
            stmt = stmt.where(scope)

        if employee_code:
            stmt = stmt.where(Employee.employee_code == employee_code)
        if date_from:
            stmt = stmt.where(AttendanceRecord.date >= date_from)
        if date_to:
            stmt = stmt.where(AttendanceRecord.date <= date_to)

        res = await session.execute(stmt)
        rows = res.all()

        items: list[AttendanceSummaryItem] = []
        grand_total_hours = 0.0
        grand_total_records = 0
        grand_total_incidents = 0

        for r in rows:
            tot_h = float(r.total_hours or 0.0)
            tot_rec = int(r.total_records or 0)
            tot_inc = int(r.incidents_count or 0)

            grand_total_hours += tot_h
            grand_total_records += tot_rec
            grand_total_incidents += tot_inc

            items.append(
                AttendanceSummaryItem(
                    employee_code=r.employee_code,
                    total_hours=round(tot_h, 2),
                    ordinary_hours=round(float(r.ordinary_hours or 0.0), 2),
                    night_hours=round(float(r.night_hours or 0.0), 2),
                    holiday_hours=round(float(r.holiday_hours or 0.0), 2),
                    excess_hours=round(float(r.excess_hours or 0.0), 2),
                    incidents_count=tot_inc,
                )
            )

        return AttendanceSummaryResponse(
            organization_id=current_user.organization_id,
            total_records=grand_total_records,
            total_hours=round(grand_total_hours, 2),
            total_incidents=grand_total_incidents,
            items=items,
        )

    @staticmethod
    async def justify_incident(
        session: AsyncSession,
        current_user: AuthenticatedUser,
        record_id: UUID,
        data: IncidentJustifyRequest,
    ) -> IncidentResponse:
        """Resolve and justify an attendance incident with supervisor attribution.

        Mitigates IDOR by verifying record belongs to current tenant.
        """
        if current_user.role not in (UserRole.ADMIN, UserRole.SUPERVISOR):
            raise AuthorizationError("Only Supervisors and Administrators can justify incidents")

        # Retrieve record with employee to enforce tenant boundary
        stmt = (
            select(AttendanceRecord)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .options(selectinload(AttendanceRecord.incidents))
            .where(
                AttendanceRecord.id == record_id,
                Employee.organization_id == current_user.organization_id,
            )
        )
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()

        if record is None:
            raise ResourceNotFoundError(
                f"Attendance record '{record_id}' not found in your organization"
            )

        incident = Incident(
            attendance_record_id=record.id,
            supervisor_id=current_user.id,
            reason=data.reason,
            status=data.status,
            reviewed_at=datetime.now(UTC),
        )
        session.add(incident)

        # If approved, update has_incident status
        if data.status == IncidentStatus.APPROVED:
            record.has_incident = False

        await session.flush()

        return IncidentResponse(
            id=incident.id,
            reason=incident.reason,
            status=incident.status,
            supervisor_id=incident.supervisor_id,
            reviewed_at=incident.reviewed_at,
        )

    @staticmethod
    async def generate_attendance_report(
        session: AsyncSession,
        current_user: AuthenticatedUser,
        employee_code: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> BytesIO:
        """Generate Excel workbook stream for tenant records."""
        records = await AttendanceService.get_attendance_records(
            session=session,
            current_user=current_user,
            employee_code=employee_code,
            date_from=date_from,
            date_to=date_to,
            limit=50000,
        )

        rows: list[dict[str, object]] = []
        for r in records:
            rows.append(
                {
                    "employee_code": r.employee_code,
                    "date": r.date,
                    "punch_in": r.punch_in,
                    "punch_out": r.punch_out,
                    "total_hours": round(r.ordinary_hours + r.excess_hours, 2),
                    "ordinary_hours": r.ordinary_hours,
                    "night_hours": r.night_hours,
                    "holiday_hours": r.holiday_hours,
                    "excess_hours": r.excess_hours,
                    "has_incident": r.has_incident,
                    "incident_type": (r.incidents[0].status.value if r.incidents else None),
                    "source_rows": "-",
                }
            )

        df = pd.DataFrame(rows)
        return export_attendance_to_excel(df)

    @staticmethod
    def get_biometric_template() -> BytesIO:
        """Generate Excel template stream for bulk biometric punches import."""
        return generate_biometric_template()

    @staticmethod
    async def _calculate_shift_hours(
        session: AsyncSession,
        organization_id: UUID,
        punch_in: datetime,
        punch_out: datetime,
    ) -> tuple[float, float, float, float]:
        """Compute ordinary, night, holiday, and excess hours for a single shift."""
        holidays_stmt = select(Holiday.date).where(Holiday.organization_id == organization_id)
        holidays_res = await session.execute(holidays_stmt)
        holiday_dates: list[date] = list(holidays_res.scalars().all())

        # Ensure consistent timezone awareness across SQLite (naive) and PostgreSQL (aware)
        p_in_dt = punch_in if punch_in.tzinfo is not None else punch_in.replace(tzinfo=UTC)
        p_out_dt = punch_out if punch_out.tzinfo is not None else punch_out.replace(tzinfo=UTC)

        p_in = pd.Series([pd.Timestamp(p_in_dt).tz_localize(None)])
        p_out = pd.Series([pd.Timestamp(p_out_dt).tz_localize(None)])
        duration_hours = max(0.0, (p_out_dt - p_in_dt).total_seconds() / 3600.0)

        night_s = compute_night_hours_vectorized(p_in, p_out)
        night_h = round(float(night_s.iloc[0]), 2)

        holiday_s = compute_holiday_hours_vectorized(p_in, p_out, holiday_dates)
        holiday_h = round(float(holiday_s.iloc[0]), 2)

        ord_s, exc_s = compute_labor_distribution_vectorized(pd.Series([duration_hours]))
        ord_h = round(float(ord_s.iloc[0]), 2)
        exc_h = round(float(exc_s.iloc[0]), 2)

        return ord_h, night_h, holiday_h, exc_h

    @staticmethod
    async def get_punch_status(
        session: AsyncSession,
        current_user: AuthenticatedUser,
    ) -> PunchStatusResponse:
        """Retrieve real-time shift status for the authenticated user."""
        user_stmt = select(User).where(
            User.id == current_user.id,
            User.organization_id == current_user.organization_id,
        )
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()

        if user is None or user.employee_id is None:
            return PunchStatusResponse(status="IDLE", active_record=None, last_punch=None)

        # Look for open shift where punch_in == punch_out and has_incident is True
        stmt = (
            select(AttendanceRecord, Employee.employee_code)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .options(selectinload(AttendanceRecord.incidents))
            .where(
                AttendanceRecord.employee_id == user.employee_id,
                AttendanceRecord.punch_in == AttendanceRecord.punch_out,
                AttendanceRecord.has_incident.is_(True),
            )
            .order_by(AttendanceRecord.punch_in.desc())
            .limit(1)
        )
        res = await session.execute(stmt)
        open_item = res.first()

        if open_item:
            rec, emp_code = open_item
            inc_responses = [
                IncidentResponse(
                    id=inc.id,
                    reason=inc.reason,
                    status=inc.status,
                    supervisor_id=inc.supervisor_id,
                    reviewed_at=inc.reviewed_at,
                )
                for inc in rec.incidents
            ]
            record_dto = AttendanceRecordResponse(
                id=rec.id,
                employee_code=emp_code,
                date=rec.date,
                punch_in=rec.punch_in,
                punch_out=rec.punch_out,
                ordinary_hours=rec.ordinary_hours,
                night_hours=rec.night_hours,
                holiday_hours=rec.holiday_hours,
                excess_hours=rec.excess_hours,
                has_incident=rec.has_incident,
                incidents=inc_responses,
            )
            return PunchStatusResponse(
                status="IN_PROGRESS",
                active_record=record_dto,
                last_punch=rec.punch_in,
            )

        # Otherwise find most recent punch
        last_stmt = (
            select(AttendanceRecord.punch_out)
            .where(AttendanceRecord.employee_id == user.employee_id)
            .order_by(AttendanceRecord.punch_out.desc())
            .limit(1)
        )
        last_punch = (await session.execute(last_stmt)).scalar_one_or_none()
        return PunchStatusResponse(status="IDLE", active_record=None, last_punch=last_punch)

    @staticmethod
    async def record_live_punch(
        session: AsyncSession,
        current_user: AuthenticatedUser,
        data: PunchActionRequest,
    ) -> AttendanceRecordResponse:
        """Register live worker punch (IN or OUT). Immutable by workers once recorded."""
        user_stmt = select(User).where(
            User.id == current_user.id,
            User.organization_id == current_user.organization_id,
        )
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()

        if user is None or user.employee_id is None:
            raise AuthorizationError(
                "Tu cuenta de usuario no tiene asignada una ficha de empleado para fichar."
            )

        emp_stmt = select(Employee).where(
            Employee.id == user.employee_id,
            Employee.organization_id == current_user.organization_id,
        )
        emp_res = await session.execute(emp_stmt)
        emp = emp_res.scalar_one_or_none()
        if emp is None:
            raise ResourceNotFoundError("Ficha de empleado no encontrada en tu organización.")

        now = data.timestamp or datetime.now(UTC)
        action_upper = str(data.action).upper()

        if action_upper in ("IN", "ENTRADA"):
            # Check if there is already an open shift without punch out
            open_stmt = (
                select(AttendanceRecord)
                .where(
                    AttendanceRecord.employee_id == emp.id,
                    AttendanceRecord.punch_in == AttendanceRecord.punch_out,
                    AttendanceRecord.has_incident.is_(True),
                )
                .order_by(AttendanceRecord.punch_in.desc())
                .limit(1)
            )
            existing_open = (await session.execute(open_stmt)).scalar_one_or_none()
            if existing_open is not None:
                raise AuthorizationError(
                    "Ya tienes un fichaje de entrada abierto. Registra la salida primero."
                )

            # Create new open punch record
            from uuid import uuid4

            record = AttendanceRecord(
                id=uuid4(),
                employee_id=emp.id,
                file_id=None,
                date=now.date(),
                punch_in=now,
                punch_out=now,
                ordinary_hours=0.0,
                night_hours=0.0,
                holiday_hours=0.0,
                excess_hours=0.0,
                has_incident=True,  # Remains true until punch out completes the shift
            )
            session.add(record)
            await session.flush()

        elif action_upper in ("OUT", "SALIDA"):
            # Find open shift to pair
            open_stmt = (
                select(AttendanceRecord)
                .options(selectinload(AttendanceRecord.incidents))
                .where(
                    AttendanceRecord.employee_id == emp.id,
                    AttendanceRecord.punch_in == AttendanceRecord.punch_out,
                    AttendanceRecord.has_incident.is_(True),
                )
                .order_by(AttendanceRecord.punch_in.desc())
                .limit(1)
            )
            existing_rec = (await session.execute(open_stmt)).scalar_one_or_none()

            if existing_rec is None:
                # Orphan exit punch
                from uuid import uuid4

                record = AttendanceRecord(
                    id=uuid4(),
                    employee_id=emp.id,
                    file_id=None,
                    date=now.date(),
                    punch_in=now,
                    punch_out=now,
                    ordinary_hours=0.0,
                    night_hours=0.0,
                    holiday_hours=0.0,
                    excess_hours=0.0,
                    has_incident=True,
                )
                session.add(record)
                await session.flush()
            else:
                # Pair shift and calculate hours
                existing_rec.punch_out = now
                ord_h, night_h, hol_h, exc_h = await AttendanceService._calculate_shift_hours(
                    session=session,
                    organization_id=current_user.organization_id,
                    punch_in=existing_rec.punch_in,
                    punch_out=now,
                )
                existing_rec.ordinary_hours = ord_h
                existing_rec.night_hours = night_h
                existing_rec.holiday_hours = hol_h
                existing_rec.excess_hours = exc_h
                existing_rec.has_incident = False
                await session.flush()
                record = existing_rec
        else:
            raise ValueError(f"Acción de fichaje desconocida: '{data.action}'. Usa 'IN' u 'OUT'.")

        await session.commit()

        # Reload with relationships
        stmt_reload = (
            select(AttendanceRecord, Employee.employee_code)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .options(selectinload(AttendanceRecord.incidents))
            .where(AttendanceRecord.id == record.id)
        )
        item = (await session.execute(stmt_reload)).first()
        if item is None:
            raise ResourceNotFoundError("No se pudo cargar el registro creado.")
        rec_obj, emp_code = item

        return AttendanceRecordResponse(
            id=rec_obj.id,
            employee_code=emp_code,
            date=rec_obj.date,
            punch_in=rec_obj.punch_in,
            punch_out=rec_obj.punch_out,
            ordinary_hours=rec_obj.ordinary_hours,
            night_hours=rec_obj.night_hours,
            holiday_hours=rec_obj.holiday_hours,
            excess_hours=rec_obj.excess_hours,
            has_incident=rec_obj.has_incident,
            incidents=[],
        )

    @staticmethod
    async def update_attendance_record(
        session: AsyncSession,
        current_user: AuthenticatedUser,
        record_id: UUID,
        data: AttendanceRecordUpdateRequest,
    ) -> AttendanceRecordResponse:
        """Supervisors/Admins update punch times with automatic shift recalculation."""
        if current_user.role not in (UserRole.ADMIN, UserRole.SUPERVISOR):
            raise AuthorizationError(
                "Solo los supervisores y administradores pueden modificar fichajes."
            )

        stmt = (
            select(AttendanceRecord, Employee.employee_code)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .options(selectinload(AttendanceRecord.incidents))
            .where(
                AttendanceRecord.id == record_id,
                Employee.organization_id == current_user.organization_id,
            )
        )
        res = await session.execute(stmt)
        item = res.first()
        if item is None:
            raise ResourceNotFoundError("Registro de asistencia no encontrado en tu organización.")

        record, emp_code = item

        p_in_cmp = (
            data.punch_in
            if data.punch_in.tzinfo is not None
            else data.punch_in.replace(tzinfo=UTC)
        )
        p_out_cmp = (
            data.punch_out
            if data.punch_out.tzinfo is not None
            else data.punch_out.replace(tzinfo=UTC)
        )
        if p_out_cmp < p_in_cmp:
            raise ValueError("La hora de salida no puede ser anterior a la hora de entrada.")

        ord_h, night_h, hol_h, exc_h = await AttendanceService._calculate_shift_hours(
            session=session,
            organization_id=current_user.organization_id,
            punch_in=data.punch_in,
            punch_out=data.punch_out,
        )

        record.punch_in = data.punch_in
        record.punch_out = data.punch_out
        record.date = data.punch_in.date()
        record.ordinary_hours = ord_h
        record.night_hours = night_h
        record.holiday_hours = hol_h
        record.excess_hours = exc_h
        record.has_incident = False

        if data.reason:
            incident = Incident(
                attendance_record_id=record.id,
                supervisor_id=current_user.id,
                reason=f"Rectificación manual por supervisor: {data.reason}",
                status=IncidentStatus.APPROVED,
                reviewed_at=datetime.now(UTC),
            )
            session.add(incident)
            record.incidents.append(incident)

        await session.commit()

        # Reload incidents
        res_re = await session.execute(
            select(AttendanceRecord)
            .options(selectinload(AttendanceRecord.incidents))
            .execution_options(populate_existing=True)
            .where(AttendanceRecord.id == record.id)
        )
        updated_rec = res_re.scalar_one()

        inc_responses = [
            IncidentResponse(
                id=inc.id,
                reason=inc.reason,
                status=inc.status,
                supervisor_id=inc.supervisor_id,
                reviewed_at=inc.reviewed_at,
            )
            for inc in updated_rec.incidents
        ]

        return AttendanceRecordResponse(
            id=updated_rec.id,
            employee_code=emp_code,
            date=updated_rec.date,
            punch_in=updated_rec.punch_in,
            punch_out=updated_rec.punch_out,
            ordinary_hours=updated_rec.ordinary_hours,
            night_hours=updated_rec.night_hours,
            holiday_hours=updated_rec.holiday_hours,
            excess_hours=updated_rec.excess_hours,
            has_incident=updated_rec.has_incident,
            incidents=inc_responses,
        )

    @staticmethod
    async def preview_excel_modifications(
        session: AsyncSession,
        current_user: AuthenticatedUser,
        stream: BinaryIO | BytesIO,
        original_filename: str,
    ) -> BulkDiffPreviewResponse:
        """Inspect and compare an uploaded Excel/CSV file against current database records.

        Calculates proposed changes (punch times and recalculated hours) without persisting.
        """
        file_format, _total_size = inspect_and_validate_stream(stream, original_filename)
        stream.seek(0)
        file_bytes = stream.read()
        stream.seek(0)

        # 1. Parse workbook rows
        canonical_df: pd.DataFrame
        # Check if the workbook contains our exported 'Detalle Fichajes' sheet
        is_exported_detail = False
        if file_format == "xlsx":
            try:
                wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
                if "Detalle Fichajes" in wb.sheetnames:
                    detail_df = pd.read_excel(
                        BytesIO(file_bytes),
                        sheet_name="Detalle Fichajes",
                        engine="openpyxl",
                    )
                    is_exported_detail = True
            except Exception:
                is_exported_detail = False

        if is_exported_detail:
            # Convert 'Detalle Fichajes' into pairs
            events: list[dict[str, object]] = []
            for _, r in detail_df.iterrows():
                emp_c = str(r.get("Código Empleado") or r.get("employee_code") or "").strip()
                if not emp_c or emp_c.startswith("="):
                    emp_c = emp_c.lstrip("'=")
                p_in = r.get("Entrada") or r.get("punch_in")
                p_out = r.get("Salida") or r.get("punch_out")

                if pd.notna(p_in) and str(p_in).strip() not in ("-", ""):
                    events.append({
                        "employee_code": emp_c,
                        "timestamp": pd.to_datetime(p_in, dayfirst=True),
                        "event_type": "IN",
                        "source_row": len(events) + 2,
                    })
                if pd.notna(p_out) and str(p_out).strip() not in ("-", ""):
                    events.append({
                        "employee_code": emp_c,
                        "timestamp": pd.to_datetime(p_out, dayfirst=True),
                        "event_type": "OUT",
                        "source_row": len(events) + 2,
                    })
            if not events:
                return BulkDiffPreviewResponse(
                    total_rows_inspected=0,
                    changes_count=0,
                    new_records_count=0,
                    modified_records_count=0,
                    unchanged_count=0,
                    changes=[],
                )
            canonical_df = pd.DataFrame(events)
            canonical_df["event_type"] = pd.Categorical(
                canonical_df["event_type"], categories=["IN", "OUT"]
            )
        else:
            canonical_df = normalize_attendance_file(BytesIO(file_bytes), file_format)

        # 2. Reconcile events into shifts
        holidays_stmt = select(Holiday.date).where(
            Holiday.organization_id == current_user.organization_id
        )
        holidays_res = await session.execute(holidays_stmt)
        holiday_dates: list[date] = list(holidays_res.scalars().all())

        reconciled_df = reconcile_attendance_events(canonical_df, holiday_dates=holiday_dates)

        # 3. Fetch existing employees for tenant
        emp_stmt = select(Employee).where(Employee.organization_id == current_user.organization_id)
        emp_res = await session.execute(emp_stmt)
        tenant_employees = {e.employee_code: e for e in emp_res.scalars().all()}

        # 4. Fetch existing records in tenant
        rec_stmt = (
            select(
                AttendanceRecord,
                Employee.employee_code,
                Employee.first_name,
                Employee.last_name,
            )
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(Employee.organization_id == current_user.organization_id)
        )
        rec_res = await session.execute(rec_stmt)
        existing_records_by_key: dict[tuple[str, date], tuple[AttendanceRecord, str]] = {}
        for row in rec_res.all():
            rec, emp_code, f_name, l_name = row
            full_name = f"{f_name} {l_name}".strip()
            existing_records_by_key[(emp_code, rec.date)] = (rec, full_name)

        # 5. Build Diff Comparison
        changes: list[BulkChangeItem] = []
        new_count = 0
        mod_count = 0
        unchanged_count = 0

        for _, row in reconciled_df.iterrows():
            emp_code = str(row["employee_code"]).strip()
            shift_date = row["date"]
            if pd.isna(shift_date) or not isinstance(shift_date, date):
                continue

            new_in_ts = row["punch_in"]
            new_out_ts = row["punch_out"]
            if pd.isna(new_in_ts) or pd.isna(new_out_ts):
                continue

            new_in = pd.Timestamp(new_in_ts).to_pydatetime()
            new_out = pd.Timestamp(new_out_ts).to_pydatetime()
            if new_in.tzinfo is None:
                new_in = new_in.replace(tzinfo=UTC)
            if new_out.tzinfo is None:
                new_out = new_out.replace(tzinfo=UTC)

            new_ord = round(float(row["ordinary_hours"]), 2)
            new_exc = round(float(row["excess_hours"]), 2)

            key = (emp_code, shift_date)
            emp_obj = tenant_employees.get(emp_code)
            emp_name = f"{emp_obj.first_name} {emp_obj.last_name}".strip() if emp_obj else None

            if key in existing_records_by_key:
                existing_rec, full_name = existing_records_by_key[key]
                old_in = existing_rec.punch_in
                old_out = existing_rec.punch_out
                if old_in and old_in.tzinfo is None:
                    old_in = old_in.replace(tzinfo=UTC)
                if old_out and old_out.tzinfo is None:
                    old_out = old_out.replace(tzinfo=UTC)

                # Check if punch times differ by more than 30 seconds
                in_diff = abs((new_in - old_in).total_seconds()) if old_in else 9999
                out_diff = abs((new_out - old_out).total_seconds()) if old_out else 9999

                if in_diff > 30 or out_diff > 30:
                    mod_count += 1
                    changes.append(
                        BulkChangeItem(
                            change_type="MODIFIED",
                            record_id=existing_rec.id,
                            employee_code=emp_code,
                            employee_name=full_name or emp_name,
                            date=shift_date,
                            old_punch_in=old_in,
                            old_punch_out=old_out,
                            old_ordinary_hours=round(existing_rec.ordinary_hours, 2),
                            old_excess_hours=round(existing_rec.excess_hours, 2),
                            new_punch_in=new_in,
                            new_punch_out=new_out,
                            new_ordinary_hours=new_ord,
                            new_excess_hours=new_exc,
                        )
                    )
                else:
                    unchanged_count += 1
            else:
                new_count += 1
                changes.append(
                    BulkChangeItem(
                        change_type="NEW",
                        record_id=None,
                        employee_code=emp_code,
                        employee_name=emp_name,
                        date=shift_date,
                        old_punch_in=None,
                        old_punch_out=None,
                        old_ordinary_hours=0.0,
                        old_excess_hours=0.0,
                        new_punch_in=new_in,
                        new_punch_out=new_out,
                        new_ordinary_hours=new_ord,
                        new_excess_hours=new_exc,
                    )
                )

        return BulkDiffPreviewResponse(
            total_rows_inspected=len(reconciled_df),
            changes_count=len(changes),
            new_records_count=new_count,
            modified_records_count=mod_count,
            unchanged_count=unchanged_count,
            changes=changes,
        )

    @staticmethod
    async def apply_bulk_changes(
        session: AsyncSession,
        current_user: AuthenticatedUser,
        payload: BulkApplyChangesRequest,
    ) -> int:
        """Atomically persist confirmed bulk modifications with audit trail."""
        if current_user.role not in (UserRole.ADMIN, UserRole.SUPERVISOR):
            raise AuthorizationError("Solo supervisores y administradores pueden aplicar cambios.")

        # Ensure employees exist
        emp_stmt = select(Employee).where(Employee.organization_id == current_user.organization_id)
        emp_res = await session.execute(emp_stmt)
        tenant_employees = {e.employee_code: e for e in emp_res.scalars().all()}

        applied_count = 0
        now_utc = datetime.now(UTC)

        for item in payload.changes:
            if item.change_type == "MODIFIED" and item.record_id is not None:
                rec_stmt = (
                    select(AttendanceRecord)
                    .join(Employee, AttendanceRecord.employee_id == Employee.id)
                    .where(
                        AttendanceRecord.id == item.record_id,
                        Employee.organization_id == current_user.organization_id,
                    )
                )
                rec = (await session.execute(rec_stmt)).scalar_one_or_none()
                if rec:
                    rec.punch_in = item.new_punch_in
                    rec.punch_out = item.new_punch_out
                    rec.ordinary_hours = item.new_ordinary_hours
                    rec.excess_hours = item.new_excess_hours
                    rec.has_incident = False

                    incident = Incident(
                        attendance_record_id=rec.id,
                        supervisor_id=current_user.id,
                        reason=f"Cambio masivo desde Excel: {payload.audit_reason}",
                        status=IncidentStatus.APPROVED,
                        reviewed_at=now_utc,
                    )
                    session.add(incident)
                    applied_count += 1

            elif item.change_type == "NEW":
                emp = tenant_employees.get(item.employee_code)
                if not emp:
                    emp = Employee(
                        organization_id=current_user.organization_id,
                        employee_code=item.employee_code,
                        first_name="Empleado",
                        last_name=item.employee_code,
                        weekly_contract_hours=40.0,
                    )
                    session.add(emp)
                    await session.flush()
                    tenant_employees[item.employee_code] = emp

                new_rec = AttendanceRecord(
                    employee_id=emp.id,
                    date=item.date,
                    punch_in=item.new_punch_in,
                    punch_out=item.new_punch_out,
                    ordinary_hours=item.new_ordinary_hours,
                    night_hours=0.0,
                    holiday_hours=0.0,
                    excess_hours=item.new_excess_hours,
                    has_incident=False,
                )
                session.add(new_rec)
                applied_count += 1

        await session.commit()
        return applied_count

