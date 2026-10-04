"""Parsers and file validation modules."""

from src.core.parsers.normalizer import (
    CorruptFileError,
    InvalidDataFormatError,
    MissingRequiredColumnsError,
    ParserError,
    normalize_attendance_file,
)
from src.core.parsers.validator import (
    FileSizeLimitExceededError,
    FileValidationError,
    MaliciousFileDetectedError,
    PathTraversalError,
    UnsupportedFileFormatError,
    detect_file_type_from_header,
    inspect_and_validate_stream,
    sanitize_and_resolve_storage_path,
    sanitize_dataframe_formulas,
    validate_file_size,
)

__all__ = [
    "FileValidationError",
    "FileSizeLimitExceededError",
    "UnsupportedFileFormatError",
    "MaliciousFileDetectedError",
    "PathTraversalError",
    "validate_file_size",
    "detect_file_type_from_header",
    "sanitize_and_resolve_storage_path",
    "sanitize_dataframe_formulas",
    "inspect_and_validate_stream",
    "ParserError",
    "MissingRequiredColumnsError",
    "CorruptFileError",
    "InvalidDataFormatError",
    "normalize_attendance_file",
]
