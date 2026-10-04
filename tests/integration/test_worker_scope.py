"""Integration tests: WORKER role is scoped server-side to its own Employee (BOLA)."""

from collections.abc import AsyncGenerator
from io import BytesIO
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.security.jwt import create_access_token
from src.core.security.password import hash_password
from src.db.models import Employee, Organization, User, UserRole
from src.db.session import Base, get_db_session
from src.main import create_application

CSV_PAYLOAD = (
    "codigo_empleado;fecha_hora;tipo_evento\n"
    "EMP001;2026-01-10 08:00:00;IN\n"
    "EMP001;2026-01-10 16:30:00;OUT\n"
    "EMP002;2026-01-10 21:30:00;IN\n"
    "EMP002;2026-01-11 05:45:00;OUT\n"
    "EMP003;2026-01-10 09:00:00;IN\n"
)


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
async def test_worker_only_sees_own_records(session: AsyncSession) -> None:
    """Workers see only their linked employee data and cannot widen scope via filters."""
    org = Organization(id=uuid4(), name="Empresa Scope")
    session.add(org)
    await session.flush()

    admin = User(
        id=uuid4(),
        organization_id=org.id,
        email="admin@scope.test",
        hashed_password=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add(admin)
    await session.commit()

    app = create_application()

    async def override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db_session] = override

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        files = {"file": ("f.csv", BytesIO(CSV_PAYLOAD.encode()), "text/csv")}
        up = await client.post("/attendance/upload", headers=_token(admin), files=files)
        assert up.status_code == 201

        emp1 = (
            await session.execute(select(Employee).where(Employee.employee_code == "EMP001"))
        ).scalar_one()

        linked_worker = User(
            id=uuid4(),
            organization_id=org.id,
            email="worker@scope.test",
            hashed_password=hash_password("WorkerPass123!"),
            role=UserRole.WORKER,
            is_active=True,
            employee_id=emp1.id,
        )
        unlinked_worker = User(
            id=uuid4(),
            organization_id=org.id,
            email="nolink@scope.test",
            hashed_password=hash_password("WorkerPass123!"),
            role=UserRole.WORKER,
            is_active=True,
        )
        session.add_all([linked_worker, unlinked_worker])
        await session.commit()

        w_headers = _token(linked_worker)

        # Profile exposes linked employee code
        me = await client.get("/auth/me", headers=w_headers)
        assert me.status_code == 200
        assert me.json()["employee_code"] == "EMP001"

        # Records: only own data
        recs = (await client.get("/attendance/records", headers=w_headers)).json()
        assert len(recs) == 1
        assert {r["employee_code"] for r in recs} == {"EMP001"}

        # Attempt to widen scope via query parameter -> empty, never other employees
        other = await client.get(
            "/attendance/records", headers=w_headers, params={"employee_code": "EMP002"}
        )
        assert other.status_code == 200
        assert other.json() == []

        # Summary: only own aggregates
        summary = (await client.get("/attendance/summary", headers=w_headers)).json()
        assert [i["employee_code"] for i in summary["items"]] == ["EMP001"]

        # Unlinked worker sees nothing
        none_recs = await client.get("/attendance/records", headers=_token(unlinked_worker))
        assert none_recs.json() == []

        # Workers cannot upload nor justify
        files = {"file": ("f.csv", BytesIO(CSV_PAYLOAD.encode()), "text/csv")}
        denied = await client.post("/attendance/upload", headers=w_headers, files=files)
        assert denied.status_code == 403
        justify = await client.post(
            f"/attendance/incidents/{recs[0]['id']}/justify",
            headers=w_headers,
            json={"reason": "Intento no autorizado", "status": "APPROVED"},
        )
        assert justify.status_code == 403
