"""Holiday ORM model for regional and company holiday calendars."""

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Date, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base

if TYPE_CHECKING:
    from src.db.models.organization import Organization


class Holiday(Base):
    """Calendar holiday entity used for vectorized surcharge calculation."""

    __tablename__ = "holidays"

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
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="holidays")

    __table_args__ = (
        UniqueConstraint("organization_id", "date", name="uq_org_holiday_date"),
        Index("ix_holidays_organization_id", "organization_id"),
        Index("ix_holidays_date", "date"),
    )
