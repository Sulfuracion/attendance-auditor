"""Unit tests for secure file ingestion, magic number verification, and normalization."""

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from src.core.parsers.normalizer import (
    InvalidDataFormatError,
    MissingRequiredColumnsError,
    detect_csv_delimiter,
    normalize_attendance_file,
)
from src.core.parsers.validator import (
    FileSizeLimitExceededError,
    FileValidationError,
    MaliciousFileDetectedError,
    detect_file_type_from_header,
    inspect_and_validate_stream,
    sanitize_and_resolve_storage_path,
    sanitize_dataframe_formulas,
    validate_file_size,
)


def test_validate_file_size() -> None:
    """Test size boundary validation."""
    validate_file_size(1024, max_bytes=2048)

    with pytest.raises(FileValidationError, match="0 bytes"):
        validate_file_size(0)

    with pytest.raises(FileSizeLimitExceededError, match="exceeds maximum"):
        validate_file_size(5000, max_bytes=4000)


def test_detect_file_type_from_header_magic_numbers() -> None:
    """Test identification of valid formats and rejection of disguised binaries."""
    # Valid XLSX PKZip header
    xlsx_header = b"PK\x03\x04\x14\x00\x06\x00"
    assert detect_file_type_from_header(xlsx_header) == "xlsx"

    # Valid CSV plain text
    csv_header = b"codigo_empleado;fecha_hora;tipo_evento\nEMP001;2026-01-01 08:00;IN"
    assert detect_file_type_from_header(csv_header) == "csv"

    # Malicious Windows PE / DOS executable disguised with .csv extension
    pe_header = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00"
    with pytest.raises(MaliciousFileDetectedError, match="DOS/Windows Executable"):
        detect_file_type_from_header(pe_header)

    # Malicious Linux ELF executable
    elf_header = b"\x7fELF\x02\x01\x01\x00"
    with pytest.raises(MaliciousFileDetectedError, match="Linux ELF"):
        detect_file_type_from_header(elf_header)

    # Corrupt binary with null bytes disguised as text
    null_bytes = b"header,col1,col2\x00\x00\x00some_payload"
    with pytest.raises(MaliciousFileDetectedError, match="null bytes"):
        detect_file_type_from_header(null_bytes)


def test_sanitize_and_resolve_storage_path(tmp_path: Path) -> None:
    """Test mitigation of directory traversal tokens in uploaded filenames."""
    # Normal filename
    path = sanitize_and_resolve_storage_path(tmp_path, "report.csv", "csv")
    assert path.parent == tmp_path.resolve()
    assert path.suffix == ".csv"
    assert len(path.stem) == 32  # UUID4 hex length

    # Malicious Path Traversal attempts
    traversal_filename = "../../../etc/passwd"
    safe_path = sanitize_and_resolve_storage_path(tmp_path, traversal_filename, "csv")
    assert safe_path.parent == tmp_path.resolve()
    assert "etc" not in str(safe_path)
    assert "passwd" not in str(safe_path)


def test_sanitize_dataframe_formulas() -> None:
    """Test vectorized mitigation of CSV/Excel formula injection."""
    raw_df = pd.DataFrame(
        {
            "codigo": ["=cmd|' /C calc'!A0", "+12345", "-SUM(A1:A10)", "@SUM", "NORMAL"],
            "notas": ["Normal text", "=HYPERLINK('http://evil.com')", "hello", "world", "ok"],
        }
    )

    clean_df = sanitize_dataframe_formulas(raw_df)

    assert clean_df["codigo"].iloc[0].startswith("'=")
    assert clean_df["codigo"].iloc[1].startswith("'+")
    assert clean_df["codigo"].iloc[2].startswith("'-")
    assert clean_df["codigo"].iloc[3].startswith("'@")
    assert clean_df["codigo"].iloc[4] == "NORMAL"
    assert clean_df["notas"].iloc[1].startswith("'=")


def test_detect_csv_delimiter() -> None:
    """Test delimiter sniffing for semicolon, comma, and tab."""
    semi_csv = "emp;time;event\n1;2;IN\n3;4;OUT"
    assert detect_csv_delimiter(semi_csv) == ";"

    comma_csv = "emp,time,event\n1,2,IN\n3,4,OUT"
    assert detect_csv_delimiter(comma_csv) == ","

    tab_csv = "emp\ttime\tevent\n1\t2\tIN\n3\t4\tOUT"
    assert detect_csv_delimiter(tab_csv) == "\t"


def test_normalize_attendance_file_csv_heterogeneous_formats() -> None:
    """Test parsing CSV with European headers, mixed date formats, and event aliases."""
    csv_content = (
        "codigo_empleado;fecha_hora;tipo_evento\n"
        "EMP001;2026-01-10 08:00:00;ENTRADA\n"
        "EMP001;10/01/2026 16:30:00;SALIDA\n"
        "EMP002;2026/01/10 22:00;E\n"
        "EMP002;11-01-2026 06:00:00;S\n"
    )
    stream = BytesIO(csv_content.encode("utf-8"))

    df = normalize_attendance_file(stream, "csv")

    assert len(df) == 4
    assert list(df.columns) == ["employee_code", "timestamp", "event_type", "source_row"]
    assert df["event_type"].tolist() == ["IN", "OUT", "IN", "OUT"]
    assert str(df["timestamp"].dtype) == "datetime64[ns]"


def test_normalize_attendance_file_missing_columns() -> None:
    """Test that missing required columns raise MissingRequiredColumnsError."""
    bad_csv = "col_a;col_b;col_c\n1;2;3"
    stream = BytesIO(bad_csv.encode("utf-8"))

    with pytest.raises(MissingRequiredColumnsError):
        normalize_attendance_file(stream, "csv")


def test_normalize_attendance_file_corrupt_timestamps() -> None:
    """Test that unparseable timestamp raises InvalidDataFormatError."""
    bad_csv = "codigo;fecha_hora;tipo\nEMP001;NOT_A_DATE;IN"
    stream = BytesIO(bad_csv.encode("utf-8"))

    with pytest.raises(InvalidDataFormatError, match="Invalid timestamp"):
        normalize_attendance_file(stream, "csv")


def test_inspect_and_validate_stream() -> None:
    """Test stream validation end-to-end."""
    valid_csv = b"employee_code,timestamp,event_type\nEMP1,2026-01-01 08:00:00,IN\n"
    stream = BytesIO(valid_csv)

    fmt, size = inspect_and_validate_stream(stream, "test.csv")
    assert fmt == "csv"
    assert size == len(valid_csv)
    # Ensure stream was rewound
    assert stream.tell() == 0
