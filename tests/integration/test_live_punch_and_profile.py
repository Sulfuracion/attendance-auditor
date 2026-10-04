"""Integration tests for live punching, worker immutability, and supervisor rectification."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.security.jwt import create_access_token
from src.core.security.password import hash_password
from src.db.models import Employee, Organization, User, UserRole
from src.db.session import Base, get_db_session
from src.main import create_application


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Isolated in-memory SQLite session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


def _token(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id, organization_id=user.organization_id, role=user.role.value
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_live_punch_worker_immutability_and_supervisor_edit(session: AsyncSession) -> None:
    """Test full cycle:

    1. Worker clocks IN and OUT.
    2. Worker cannot update record (403 Forbidden).
    3. Supervisor rectifies record with automatic hours recalculation.
    4. Profile and password change workflow.
    """
    org = Organization(id=uuid4(), name="Empresa Test S.L.")
    session.add(org)
    await session.flush()

    emp = Employee(
        id=uuid4(),
        organization_id=org.id,
        employee_code="EMP_TEST",
        first_name="Juan",
        last_name="Pérez",
        weekly_contract_hours=40.0,
    )
    session.add(emp)
    await session.flush()

    worker = User(
        id=uuid4(),
        organization_id=org.id,
        email="worker@empresatest.com",
        hashed_password=hash_password("WorkerPass123!"),
        role=UserRole.WORKER,
        is_active=True,
        employee_id=emp.id,
    )
    supervisor = User(
        id=uuid4(),
        organization_id=org.id,
        email="supervisor@empresatest.com",
        hashed_password=hash_password("SupervisorPass123!"),
        role=UserRole.SUPERVISOR,
        is_active=True,
    )
    session.add_all([worker, supervisor])
    await session.commit()

    app = create_application()

    async def override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db_session] = override

    w_headers = _token(worker)
    s_headers = _token(supervisor)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # 1. Initial Punch Status: IDLE
        status_res = await client.get("/attendance/punch/status", headers=w_headers)
        assert status_res.status_code == 200
        assert status_res.json()["status"] == "IDLE"

        # 2. Worker clocks IN
        now = datetime.now(UTC)
        punch_in_res = await client.post(
            "/attendance/punch",
            headers=w_headers,
            json={"action": "IN", "timestamp": now.isoformat()},
        )
        assert punch_in_res.status_code == 201
        record_id = punch_in_res.json()["id"]

        # Check status: IN_PROGRESS
        status_in_progress = await client.get("/attendance/punch/status", headers=w_headers)
        assert status_in_progress.status_code == 200
        assert status_in_progress.json()["status"] == "IN_PROGRESS"

        # 3. Worker clocks OUT (8 hours later)
        later = now + timedelta(hours=8)
        punch_out_res = await client.post(
            "/attendance/punch",
            headers=w_headers,
            json={"action": "OUT", "timestamp": later.isoformat()},
        )
        assert punch_out_res.status_code == 201
        rec_data = punch_out_res.json()
        assert rec_data["ordinary_hours"] == 8.0
        assert rec_data["has_incident"] is False

        # Status returns to IDLE
        status_idle = await client.get("/attendance/punch/status", headers=w_headers)
        assert status_idle.json()["status"] == "IDLE"

        # 4. Immutability: Worker attempts to modify punch times -> 403 Forbidden
        edit_payload = {
            "punch_in": now.isoformat(),
            "punch_out": (now + timedelta(hours=9)).isoformat(),
            "reason": "Intento de cambiar horas por mi cuenta",
        }
        forbidden_edit = await client.put(
            f"/attendance/records/{record_id}",
            headers=w_headers,
            json=edit_payload,
        )
        assert forbidden_edit.status_code == 403

        # 5. Supervisor Rectification: Allowed and recalculates hours
        super_edit = await client.put(
            f"/attendance/records/{record_id}",
            headers=s_headers,
            json=edit_payload,
        )
        assert super_edit.status_code == 200
        updated = super_edit.json()
        assert updated["ordinary_hours"] == 8.0
        assert updated["excess_hours"] == 1.0  # 9h worked -> 8h ord + 1h excess
        assert len(updated["incidents"]) == 1

        # 6. Profile update
        prof_res = await client.get("/auth/me", headers=w_headers)
        assert prof_res.status_code == 200
        assert prof_res.json()["organization_name"] == "Empresa Test S.L."

        upd_prof = await client.put(
            "/auth/profile",
            headers=w_headers,
            json={"first_name": "Juan Carlos", "last_name": "Pérez Gómez"},
        )
        assert upd_prof.status_code == 200
        assert upd_prof.json()["first_name"] == "Juan Carlos"
