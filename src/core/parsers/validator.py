"""Secure file ingestion, magic byte verification, and path traversal mitigation.

Implements boundary defense against:
- Malicious file types and disguised binaries (MZ, ELF, Mach-O).
- Path traversal vulnerabilities by enforcing canonical UUID-based naming and path resolution.
- Spreadsheet/CSV formula injection attacks.
- DoS via file size limits.
"""

import re
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import uuid4

import pandas as pd

from src.config import get_settings

# Magic numbers for known file formats
ZIP_XLSX_MAGIC = b"PK\x03\x04"
EXECUTABLE_SIGNATURES = [
    (b"MZ", "DOS/Windows Executable"),
    (b"\x7fELF", "Linux ELF Executable"),
    (b"\xfe\xed\xfa\xce", "Mach-O 32-bit"),
    (b"\xfe\xed\xfa\xcf", "Mach-O 64-bit"),
    (b"\xce\xfa\xed\xfe", "Mach-O 32-bit (reverse)"),
    (b"\xcf\xfa\xed\xfe", "Mach-O 64-bit (reverse)"),
    (b"\xca\xfe\xba\xbe", "Java Class / Mach-O Fat"),
]

# Regex detecting potential CSV/Excel formula injection starters
FORMULA_PREFIX_REGEX = re.compile(r"^[\=\+\-\@\t\r]")


class FileValidationError(Exception):
    """Base exception for file ingestion security and format validation failures."""

    pass


class FileSizeLimitExceededError(FileValidationError):
    """Raised when an uploaded file exceeds the configured maximum size limit."""

    pass


class UnsupportedFileFormatError(FileValidationError):
    """Raised when the file format or MIME type is not allowed."""

    pass


class MaliciousFileDetectedError(FileValidationError):
    """Raised when executable headers or dangerous binary signatures are detected."""

    pass


class PathTraversalError(FileValidationError):
    """Raised when a filename or storage path attempts directory traversal."""

    pass


def validate_file_size(size_bytes: int, max_bytes: int | None = None) -> None:
    """Validate that the file size is within permitted boundaries.

    Args:
        size_bytes: Actual size of the file in bytes.
        max_bytes: Optional limit override; defaults to settings.MAX_UPLOAD_SIZE_BYTES.

    Raises:
        FileSizeLimitExceededError: If the file exceeds the allowed limit.
        FileValidationError: If the file is 0 bytes.
    """
    limit = max_bytes if max_bytes is not None else get_settings().MAX_UPLOAD_SIZE_BYTES
    if size_bytes <= 0:
        raise FileValidationError("File is empty (0 bytes)")
    if size_bytes > limit:
        raise FileSizeLimitExceededError(
            f"File size ({size_bytes} bytes) exceeds maximum permitted limit ({limit} bytes)"
        )


def detect_file_type_from_header(header: bytes) -> Literal["xlsx", "csv"]:
    """Inspect magic numbers and byte signatures to verify true file format.

    Args:
        header: The first 512+ bytes of the uploaded file.

    Returns:
        Detected valid format literal ('xlsx' or 'csv').

    Raises:
        MaliciousFileDetectedError: If an executable binary header is encountered.
        UnsupportedFileFormatError: If neither valid XLSX nor safe text CSV is detected.
    """
    if not header:
        raise UnsupportedFileFormatError("Cannot determine file type from empty header")

    # Check for executable magic numbers
    for signature, name in EXECUTABLE_SIGNATURES:
        if header.startswith(signature):
            raise MaliciousFileDetectedError(
                f"Malicious file header detected: disguises a {name} binary"
            )

    # XLSX is stored as a PKZip archive containing XML definitions
    if header.startswith(ZIP_XLSX_MAGIC):
        return "xlsx"

    # CSV / Text validation:
    # Safe text should not contain null bytes (null byte is a strong binary indicator)
    if b"\x00" in header:
        raise MaliciousFileDetectedError(
            "Binary content or null bytes detected in non-spreadsheet file"
        )

    # Check if header can be decoded into text (UTF-8, UTF-8-BOM, or latin-1)
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            header.decode(encoding)
            return "csv"
        except UnicodeDecodeError:
            continue

    raise UnsupportedFileFormatError("File header is neither a valid Excel XLSX nor readable CSV")


def sanitize_and_resolve_storage_path(
    storage_root: Path,
    _original_filename: str,
    detected_format: Literal["xlsx", "csv"],
) -> Path:
    """Mitigate Path Traversal by generating a canonical UUID filename within a secured root.

    Args:
        storage_root: The authorized root directory for uploads.
        original_filename: The user-supplied filename (untrusted input).
        detected_format: The verified format extension.

    Returns:
        Canonical, resolved Path object strictly inside storage_root.

    Raises:
        PathTraversalError: If traversal tokens or escapes from storage_root are detected.
    """
    # Ensure storage root exists and resolve canonical absolute path
    storage_root_resolved = storage_root.resolve()
    storage_root_resolved.mkdir(parents=True, exist_ok=True)

    # Discard user-supplied filename completely for storage, use pure UUID4 + verified ext
    canonical_filename = f"{uuid4().hex}.{detected_format}"
    target_path = (storage_root_resolved / canonical_filename).resolve()

    # Validate that resolved target_path is strictly within storage_root_resolved
    try:
        target_path.relative_to(storage_root_resolved)
    except ValueError as e:
        raise PathTraversalError("Target storage path resolves outside authorized root") from e

    return target_path


def sanitize_formula_injection_cell(value: object) -> object:
    """Neutralize formula injection on a single cell value if it is a string."""
    if isinstance(value, str) and FORMULA_PREFIX_REGEX.match(value):
        return f"'{value}"
    return value


def sanitize_dataframe_formulas(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized neutralization of CSV/Excel formula injection attacks across all text columns.

    Any cell starting with '=', '+', '-', '@', '\t', or '\r' is prefixed with a single quote (').
    """
    clean_df = df.copy()
    for col in clean_df.select_dtypes(include=["object", "string"]).columns:
        clean_df[col] = (
            clean_df[col].astype(str).str.replace(r"^([\=\+\-\@\t\r])", r"'\1", regex=True)
        )
    return clean_df


def inspect_and_validate_stream(
    stream: BinaryIO | BytesIO,
    _original_filename: str,
    max_bytes: int | None = None,
) -> tuple[Literal["xlsx", "csv"], int]:
    """Inspect and validate an open binary stream without exhausting memory unnecessarily.

    Args:
        stream: Binary stream of the incoming file.
        _original_filename: Untrusted filename for logging/inspection.
        max_bytes: Maximum size allowed.

    Returns:
        Tuple of (verified file format literal, total byte size).
    """
    # Read first 512 bytes for header analysis
    header = stream.read(512)
    stream.seek(0, 2)  # Seek to end
    total_size = stream.tell()
    stream.seek(0)  # Rewind to beginning

    validate_file_size(total_size, max_bytes=max_bytes)
    detected_format = detect_file_type_from_header(header)

    return detected_format, total_size
