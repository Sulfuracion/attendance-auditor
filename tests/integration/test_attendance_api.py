"""Integration tests for the complete attendance auditing workflow."""

from collections.abc import AsyncGenerator
from io import BytesIO
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.security.jwt import create_access_token
from src.core.security.password import hash_password
from src.db.models import Organization, User, UserRole
from src.db.session import Base, get_db_session
from src.main import create_application


@pytest_asyncio.fixture
async def async_test_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated, in-memory SQLite database session for integration tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def setup_test_context(
    async_test_session: AsyncSession,
) -> dict[str, Any]:
    """Create test organization, admin user, and valid JWT token."""
    session = async_test_session

    org_a = Organization(id=uuid4(), name="Empresa Test A")
    org_b = Organization(id=uuid4(), name="Empresa Test B")
    session.add_all([org_a, org_b])
    await session.flush()

    admin_user = User(
        id=uuid4(),
        organization_id=org_a.id,
        email="admin@empresatest.com",
        hashed_password=hash_password("AdminSecurePassword123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add(admin_user)
    await session.commit()

    token = create_access_token(
        user_id=admin_user.id,
        organization_id=org_a.id,
        role=admin_user.role.value,
    )

    return {
        "org_a_id": org_a.id,
        "org_b_id": org_b.id,
        "admin_id": admin_user.id,
        "token": token,
    }


@pytest.mark.asyncio
async def test_full_attendance_lifecycle_flow(
    async_test_session: AsyncSession,
    setup_test_context: dict[str, Any],
) -> None:
    """Full HTTP workflow integration test:

    1. Upload CSV with normal, night, and incident punches.
    2. Query reconciled records.
    3. Query aggregated analytics summary.
    4. Justify detected incident.
    5. Download and verify formatted Excel report.
    """
    app = create_application()

    # Override database session dependency to use test session
    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield async_test_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    token = setup_test_context["token"]
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # ----------------------------------------------------------------------
        # 1. Upload attendance CSV file
        # ----------------------------------------------------------------------
        csv_payload = (
            "codigo_empleado;fecha_hora;tipo_evento\n"
            "EMP001;2026-01-10 08:00:00;IN\n"
            "EMP001;2026-01-10 16:30:00;OUT\n"
            "EMP002;2026-01-10 21:30:00;IN\n"
            "EMP002;2026-01-11 05:45:00;OUT\n"
            "EMP003;2026-01-10 09:00:00;IN\n"  # Orphan IN (missing exit)
        )
        files = {
            "file": (
                "fichajes_enero.csv",
                BytesIO(csv_payload.encode("utf-8")),
                "text/csv",
            )
        }

        upload_res = await client.post("/attendance/upload", headers=headers, files=files)
        assert upload_res.status_code == 201
        upload_data = upload_res.json()
        assert upload_data["total_rows_processed"] == 5
        assert upload_data["reconciled_shifts"] == 2
        assert upload_data["incidents_detected"] == 1
        assert upload_data["status"] == "PROCESSED"

        # ----------------------------------------------------------------------
        # 2. Query reconciled records
        # ----------------------------------------------------------------------
        records_res = await client.get("/attendance/records", headers=headers)
        assert records_res.status_code == 200
        records = records_res.json()
        assert len(records) == 3

        # Locate EMP002 (night shift crossing midnight)
        emp2_record = next(r for r in records if r["employee_code"] == "EMP002")
        assert emp2_record["night_hours"] == 7.75
        assert emp2_record["has_incident"] is False

        # Locate EMP003 (incident)
        emp3_record = next(r for r in records if r["employee_code"] == "EMP003")
        assert emp3_record["has_incident"] is True
        incident_record_id = emp3_record["id"]

        # ----------------------------------------------------------------------
        # 3. Query aggregated analytics summary
        # ----------------------------------------------------------------------
        summary_res = await client.get("/attendance/summary", headers=headers)
        assert summary_res.status_code == 200
        summary_data = summary_res.json()
        assert summary_data["total_records"] == 3
        assert summary_data["total_incidents"] == 1
        assert len(summary_data["items"]) == 3

        # ----------------------------------------------------------------------
        # 4. Justify detected incident
        # ----------------------------------------------------------------------
        justify_payload = {
            "reason": "Trabajador olvidó fichar salida por corte de luz general en planta",
            "status": "APPROVED",
        }
        justify_res = await client.post(
            f"/attendance/incidents/{incident_record_id}/justify",
            headers=headers,
            json=justify_payload,
        )
        assert justify_res.status_code == 200
        justify_data = justify_res.json()
        assert justify_data["status"] == "APPROVED"
        assert "corte de luz" in justify_data["reason"]

        # Verify incident status updated on records query
        updated_records_res = await client.get("/attendance/records", headers=headers)
        assert updated_records_res.status_code == 200
        updated_records = updated_records_res.json()
        emp3_updated = next(r for r in updated_records if r["id"] == incident_record_id)
        assert emp3_updated["has_incident"] is False
        assert len(emp3_updated["incidents"]) == 1

        # ----------------------------------------------------------------------
        # 5. Export and verify Excel report
        # ----------------------------------------------------------------------
        export_res = await client.get("/attendance/export", headers=headers)
        assert export_res.status_code == 200
        assert "spreadsheetml.sheet" in export_res.headers.get("content-type", "")
        assert len(export_res.content) > 1000

        # ----------------------------------------------------------------------
        # 6. Download biometric template and verify headers
        # ----------------------------------------------------------------------
        template_res = await client.get("/attendance/template", headers=headers)
        assert template_res.status_code == 200
        assert "spreadsheetml.sheet" in template_res.headers.get("content-type", "")
        assert 'filename="plantilla_fichajes_biometricos.xlsx"' in template_res.headers.get(
            "content-disposition", ""
        )
        assert len(template_res.content) > 1000

        # ----------------------------------------------------------------------
        # 7. Bulk Excel Diff Preview and Apply Confirmation
        # ----------------------------------------------------------------------
        # Upload a modified file for EMP001 changing punch times to 08:00 - 18:00 (10h)
        modified_csv = (
            "codigo_empleado;fecha_hora;tipo_evento\n"
            "EMP001;2026-01-10 08:00:00;IN\n"
            "EMP001;2026-01-10 18:00:00;OUT\n"
        )
        mod_stream = BytesIO(modified_csv.encode("utf-8"))
        preview_res = await client.post(
            "/attendance/preview-changes",
            headers=headers,
            files={"file": ("cambios_masivos.csv", mod_stream, "text/csv")},
        )
        assert preview_res.status_code == 200
        preview_data = preview_res.json()
        assert preview_data["changes_count"] == 1
        assert preview_data["modified_records_count"] == 1
        diff_item = preview_data["changes"][0]
        assert diff_item["employee_code"] == "EMP001"
        assert diff_item["new_ordinary_hours"] == 8.0
        assert diff_item["new_excess_hours"] == 2.0

        # Apply confirmed changes
        apply_payload = {
            "changes": preview_data["changes"],
            "audit_reason": "Corrección de turno acordada por gerencia",
        }
        apply_res = await client.post(
            "/attendance/apply-changes",
            headers=headers,
            json=apply_payload,
        )
        assert apply_res.status_code == 200
        assert apply_res.json()["applied_count"] == 1


