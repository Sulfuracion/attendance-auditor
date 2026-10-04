"""Fault-tolerant attendance file normalizer.

Converts heterogeneous CSV (autodetecting delimiters ',', ';', '\t') and Excel (XLSX)
data into a strictly typed, canonical attendance event stream DataFrame:
- employee_code: str
- timestamp: datetime64[ns]
- event_type: Categorical['IN', 'OUT']
- source_row: int
"""

import csv
from io import BytesIO, StringIO
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd

# Synonyms for header resolution
HEADER_SYNONYMS: dict[str, list[str]] = {
    "employee_code": [
        "employee_code",
        "codigo_empleado",
        "codigo",
        "cod_empleado",
        "id_empleado",
        "badge",
        "worker_id",
        "legajo",
        "dni",
        "id",
        "empleado",
        "user_id",
        "matricula",
    ],
    "timestamp": [
        "timestamp",
        "fecha_hora",
        "fechahora",
        "datetime",
        "date_time",
        "fichaje",
        "punch_time",
        "marca",
        "marcas",
    ],
    "event_type": [
        "event_type",
        "tipo_evento",
        "tipo",
        "tipo_fichaje",
        "type",
        "sentido",
        "accion",
        "direction",
        "estado",
        "in_out",
        "e_s",
    ],
}

EVENT_IN_ALIASES = {
    "IN",
    "ENTRADA",
    "E",
    "1",
    "CHECKIN",
    "CHECK-IN",
    "INGRESO",
    "ENTR",
    "START",
    "ENT",
}
EVENT_OUT_ALIASES = {
    "OUT",
    "SALIDA",
    "S",
    "0",
    "CHECKOUT",
    "CHECK-OUT",
    "EGRESO",
    "SAL",
    "END",
    "SALID",
}


class ParserError(Exception):
    """Base exception for parsing and normalization failures."""

    pass


class MissingRequiredColumnsError(ParserError):
    """Raised when canonical columns cannot be resolved from the input headers."""

    pass


class CorruptFileError(ParserError):
    """Raised when the input file structure cannot be read or is corrupted."""

    pass


class InvalidDataFormatError(ParserError):
    """Raised when essential fields cannot be converted to expected types."""

    pass


def detect_csv_delimiter(sample_text: str) -> str:
    """Detect delimiter (',', ';', '\t', '|') by statistical inspection or csv.Sniffer."""
    delimiters_str = ",;\t|"
    first_lines = [line for line in sample_text.splitlines() if line.strip()][:5]
    if not first_lines:
        return ","

    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff("\n".join(first_lines), delimiters=delimiters_str)
        return str(dialect.delimiter)
    except Exception:
        # Fallback: Count occurrences in header line
        header = first_lines[0]
        delimiters = [";", ",", "\t", "|"]
        counts = {d: header.count(d) for d in delimiters}
        best_delim = max(counts, key=counts.get)  # type: ignore[arg-type]
        return best_delim if counts[best_delim] > 0 else ","


def resolve_column_mappings(df_columns: list[str]) -> dict[str, str]:
    """Map detected input column names to canonical target names."""
    normalized_cols = {str(col).strip().lower().replace(" ", "_"): col for col in df_columns}
    resolved: dict[str, str] = {}

    for canonical_name, synonyms in HEADER_SYNONYMS.items():
        matched_source: str | None = None
        for synonym in synonyms:
            if synonym in normalized_cols:
                matched_source = normalized_cols[synonym]
                break

        if matched_source is not None:
            resolved[canonical_name] = matched_source

    missing = [c for c in ("employee_code", "timestamp", "event_type") if c not in resolved]
    if missing:
        raise MissingRequiredColumnsError(
            f"Missing required columns: {missing}. Available columns: {list(df_columns)}"
        )

    return resolved


def normalize_event_type(series: pd.Series) -> pd.Series:
    """Vectorized conversion of heterogeneous event strings to Categorical['IN', 'OUT']."""
    clean_series = series.astype(str).str.strip().str.upper()

    # Vectorized boolean masks
    is_in = clean_series.isin(EVENT_IN_ALIASES)
    is_out = clean_series.isin(EVENT_OUT_ALIASES)

    # Unknown event types check
    unknown_mask = ~(is_in | is_out)
    if unknown_mask.any():
        sample_invalid = clean_series[unknown_mask].iloc[0]
        raise InvalidDataFormatError(f"Unrecognized event type value: '{sample_invalid}'")

    result = np.where(is_in, "IN", "OUT")
    return pd.Series(
        pd.Categorical(result, categories=["IN", "OUT"], ordered=False),
        index=series.index,
    )


def normalize_attendance_file(
    file_source: str | Path | BinaryIO | BytesIO,
    file_format: str,
) -> pd.DataFrame:
    """Normalize a CSV or Excel file into a strictly-typed canonical DataFrame.

    Canonical Schema:
        - employee_code: str
        - timestamp: datetime64[ns]
        - event_type: Categorical['IN', 'OUT']
        - source_row: int

    Returns:
        Sorted DataFrame ready for vectorized reconciliation.

    Raises:
        CorruptFileError: If the file is unreadable.
        MissingRequiredColumnsError: If essential columns are missing.
        InvalidDataFormatError: If values cannot be parsed to canonical types.
    """
    raw_df: pd.DataFrame
    try:
        if file_format == "xlsx":
            raw_df = pd.read_excel(file_source, engine="openpyxl")
        elif file_format == "csv":
            content: str
            if isinstance(file_source, str | Path):
                with open(file_source, encoding="utf-8-sig", errors="replace") as f:
                    content = f.read()
            elif isinstance(file_source, BytesIO | BinaryIO):
                bytes_content = file_source.read()
                file_source.seek(0)
                try:
                    content = bytes_content.decode("utf-8-sig")
                except UnicodeDecodeError:
                    content = bytes_content.decode("latin-1", errors="replace")
            else:
                raise CorruptFileError(f"Unsupported input source type: {type(file_source)}")

            delimiter = detect_csv_delimiter(content)
            raw_df = pd.read_csv(
                StringIO(content),
                sep=delimiter,
                engine="c",
                dtype=str,
                keep_default_na=False,
            )
        else:
            raise CorruptFileError(f"Unsupported file format '{file_format}'")
    except (MissingRequiredColumnsError, InvalidDataFormatError):
        raise
    except Exception as e:
        raise CorruptFileError(f"Failed to parse {file_format.upper()} file: {e}") from e

    if raw_df.empty:
        raise CorruptFileError("Attendance file contains no data rows")

    # Record 1-indexed source row numbers before filtering/sorting
    # (Assuming header is row 1, data rows start at row 2)
    raw_df["source_row"] = np.arange(2, len(raw_df) + 2, dtype=int)

    # Resolve column mappings
    mapping = resolve_column_mappings(list(raw_df.columns))

    # Construct canonical columns
    canonical_df = pd.DataFrame(index=raw_df.index)

    # 1. employee_code: string, trimmed
    canonical_df["employee_code"] = raw_df[mapping["employee_code"]].astype(str).str.strip()
    if (canonical_df["employee_code"] == "").any():
        raise InvalidDataFormatError("File contains empty employee_code values")

    # 2. timestamp: vectorized datetime64[ns] conversion
    raw_timestamps = raw_df[mapping["timestamp"]].astype(str).str.strip()
    try:
        parsed_timestamps = pd.to_datetime(
            raw_timestamps,
            format="mixed",
            dayfirst=True,
            errors="coerce",
        )
    except Exception as e:
        raise InvalidDataFormatError(f"Timestamp parsing failed: {e}") from e

    nat_mask = parsed_timestamps.isna()
    if nat_mask.any():
        invalid_sample = raw_timestamps[nat_mask].iloc[0]
        invalid_row = raw_df.loc[nat_mask, "source_row"].iloc[0]
        raise InvalidDataFormatError(f"Invalid timestamp '{invalid_sample}' at row {invalid_row}")

    # Ensure timezone-naive UTC representation for fast numpy calculations
    if parsed_timestamps.dt.tz is not None:
        parsed_timestamps = parsed_timestamps.dt.tz_convert("UTC").dt.tz_localize(None)

    canonical_df["timestamp"] = parsed_timestamps

    # 3. event_type: Categorical['IN', 'OUT']
    canonical_df["event_type"] = normalize_event_type(raw_df[mapping["event_type"]])

    # 4. source_row
    canonical_df["source_row"] = raw_df["source_row"]

    # Sort strictly by employee_code and timestamp to prepare for vectorized pairing
    canonical_df = canonical_df.sort_values(
        by=["employee_code", "timestamp"], ascending=[True, True]
    ).reset_index(drop=True)

    return canonical_df
