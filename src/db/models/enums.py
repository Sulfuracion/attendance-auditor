"""Domain enumerations for database models and schemas."""

from enum import Enum


class UserRole(str, Enum):
    """Role-Based Access Control levels."""

    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    WORKER = "WORKER"


class FileStatus(str, Enum):
    """Processing lifecycle states for ingested attendance files."""

    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class IncidentStatus(str, Enum):
    """Approval lifecycle states for attendance anomalies or justifications."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
