"""nullable_attendance_file_id

Make attendance_records.file_id nullable so manual live punches can exist.

Revision ID: e3f819b21a30
Revises: d2a7f3b91e40
Create Date: 2026-10-04 20:45:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3f819b21a30"
down_revision: str | Sequence[str] | None = "d2a7f3b91e40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Alter attendance_records.file_id to be nullable with batch mode for SQLite."""
    with op.batch_alter_table("attendance_records") as batch_op:
        batch_op.alter_column(
            "file_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )


def downgrade() -> None:
    """Revert attendance_records.file_id to NOT NULL."""
    with op.batch_alter_table("attendance_records") as batch_op:
        batch_op.alter_column(
            "file_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
