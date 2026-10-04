"""Local development seed script.

Provisions an initial organization, an administrator user with Argon2id hash,
test employees, and calendar holidays for immediate local verification.

Usage:
    poetry run python -m scripts.seed_local
"""

import asyncio
from datetime import date
from uuid import uuid4

from sqlalchemy import select

from src.core.security.password import hash_password
from src.db.models import Employee, Holiday, Organization, User, UserRole
from src.db.session import Base, async_session_factory, engine


async def seed() -> None:
    """Execute the database seeding routine."""
    print("=" * 70)
    print(" Attendance Auditor - Local Database Seeding ")
    print("=" * 70)

    # 1. Ensure all tables are created
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # 2. Organization: Empresa Demo S.L.
        org_name = "Empresa Demo S.L."
        stmt_org = select(Organization).where(Organization.name == org_name)
        res_org = await session.execute(stmt_org)
        org = res_org.scalar_one_or_none()

        if org is None:
            org = Organization(id=uuid4(), name=org_name)
            session.add(org)
            await session.flush()
            print(f"[*] Creada organización: '{org.name}' (ID: {org.id})")
        else:
            print(f"[-] Organización existente: '{org.name}' (ID: {org.id})")

        # 3. Test Users (Admin, Supervisor, Worker for RBAC testing)
        test_users = [
            ("admin@empresa.com", "AdminPass123!", UserRole.ADMIN),
            ("supervisor@empresa.com", "SupervisorPass123!", UserRole.SUPERVISOR),
            ("worker@empresa.com", "WorkerPass123!", UserRole.WORKER),
        ]

        for email, pwd, role in test_users:
            stmt_user = select(User).where(User.email == email)
            res_user = await session.execute(stmt_user)
            existing_user = res_user.scalar_one_or_none()
            if existing_user is None:
                hashed_pwd = hash_password(pwd)
                new_user = User(
                    id=uuid4(),
                    organization_id=org.id,
                    email=email,
                    hashed_password=hashed_pwd,
                    role=role,
                    is_active=True,
                )
                session.add(new_user)
                await session.flush()
                print(f"[*] Creado usuario {role.value}: '{email}'")
            else:
                print(f"[-] Usuario ya existente: '{email}' ({role.value})")

        # 4. Test Employees
        test_employees = [
            ("EMP001", "Carlos", "García López", 40.0),
            ("EMP002", "Lucía", "Martínez Soler", 40.0),
            ("EMP003", "David", "Fernández Ruiz", 35.0),
        ]

        for code, first, last, hours in test_employees:
            stmt_emp = select(Employee).where(
                Employee.organization_id == org.id,
                Employee.employee_code == code,
            )
            res_emp = await session.execute(stmt_emp)
            emp = res_emp.scalar_one_or_none()
            if emp is None:
                new_emp = Employee(
                    id=uuid4(),
                    organization_id=org.id,
                    employee_code=code,
                    first_name=first,
                    last_name=last,
                    weekly_contract_hours=hours,
                )
                session.add(new_emp)
                print(f"[*] Creado empleado: {code} - {first} {last} ({hours}h/sem)")
            else:
                print(f"[-] Empleado ya existente: {code} - {emp.first_name} {emp.last_name}")

        # 5. Test Holidays (Current Year 2026)
        test_holidays = [
            (date(2026, 1, 1), "Año Nuevo"),
            (date(2026, 5, 1), "Fiesta del Trabajo"),
        ]

        for h_date, desc in test_holidays:
            stmt_hol = select(Holiday).where(
                Holiday.organization_id == org.id,
                Holiday.date == h_date,
            )
            res_hol = await session.execute(stmt_hol)
            hol = res_hol.scalar_one_or_none()
            if hol is None:
                new_hol = Holiday(
                    id=uuid4(),
                    organization_id=org.id,
                    date=h_date,
                    description=desc,
                )
                session.add(new_hol)
                print(f"[*] Creado festivo: {h_date} - {desc}")
            else:
                print(f"[-] Festivo ya existente: {h_date} - {desc}")

        # 6. Link WORKER account to its Employee record (self-service scoping)
        await session.flush()
        worker_link_code = "EMP001"
        worker_res = await session.execute(
            select(User).where(User.email == "worker@empresa.com")
        )
        worker_user = worker_res.scalar_one_or_none()
        emp_link_res = await session.execute(
            select(Employee).where(
                Employee.organization_id == org.id,
                Employee.employee_code == worker_link_code,
            )
        )
        worker_emp = emp_link_res.scalar_one_or_none()
        if worker_user is not None and worker_emp is not None:
            if worker_user.employee_id != worker_emp.id:
                worker_user.employee_id = worker_emp.id
                print(f"[*] Vinculado worker@empresa.com -> {worker_link_code}")
            else:
                print(f"[-] worker@empresa.com ya vinculado a {worker_link_code}")

        await session.commit()

    print("=" * 70)
    print(" Semillas aplicadas correctamente con éxito! ")
    print("=" * 70)
    print("Credenciales de Acceso Local para Pruebas:")
    print("  - Admin:      admin@empresa.com      / AdminPass123!")
    print("  - Supervisor: supervisor@empresa.com / SupervisorPass123!")
    print("  - Worker:     worker@empresa.com     / WorkerPass123!")
    print(f"  - Tenant ID (Organización): {org.id}")
    print("=" * 70)


def main() -> None:
    """Entry point for seed script execution."""
    asyncio.run(seed())


if __name__ == "__main__":
    main()
