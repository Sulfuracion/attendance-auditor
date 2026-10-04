"""link_user_employee

Links User accounts to Employee records so WORKER access can be scoped
server-side to their own attendance data (BOLA mitigation).

Revision ID: d2a7f3b91e40
Revises: c1beaca1c709
Create Date: 2026-10-04 20:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2a7f3b91e40"
down_revision: str | Sequence[str] | None = "c1beaca1c709"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable users.employee_id FK (batch mode for SQLite compatibility)."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("employee_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_users_employee_id",
            "employees",
            ["employee_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Remove users.employee_id FK and column."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("fk_users_employee_id", type_="foreignkey")
        batch_op.drop_column("employee_id")
