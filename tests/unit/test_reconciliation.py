"""Unit tests and performance benchmarks for vectorized shift reconciliation."""

import time
from datetime import date
from io import BytesIO

import pandas as pd

from src.core.parsers.normalizer import normalize_attendance_file
from src.core.reconciliation.engine import reconcile_attendance_events
from src.core.rules.shifts import (
    compute_holiday_hours_vectorized,
    compute_labor_distribution_vectorized,
    compute_night_hours_vectorized,
)
from tests.fixtures.synthetic_generator import SYNTHETIC_HOLIDAYS, generate_synthetic_csv


def test_compute_night_hours_vectorized_exactness() -> None:
    """Validate 0% error on known night shifts and midnight crossings."""
    punch_ins = pd.Series(
        [
            pd.Timestamp("2026-01-10 08:00:00"),  # Day shift
            pd.Timestamp("2026-01-10 21:30:00"),  # Crosses midnight to 05:45
            pd.Timestamp("2026-01-11 04:00:00"),  # Early morning to 12:00
            pd.Timestamp("2026-01-11 22:00:00"),  # Exact night window to 06:00
            pd.Timestamp("2026-01-12 23:00:00"),  # 23:00 to 07:00 next day
        ]
    )
    punch_outs = pd.Series(
        [
            pd.Timestamp("2026-01-10 16:00:00"),  # 8h duration, 0h night
            pd.Timestamp("2026-01-11 05:45:00"),  # 8.25h duration, 7.75h night (22:00 to 05:45)
            pd.Timestamp("2026-01-11 12:00:00"),  # 8h duration, 2h night (04:00 to 06:00)
            pd.Timestamp("2026-01-12 06:00:00"),  # 8h duration, 8h night (22:00 to 06:00)
            pd.Timestamp("2026-01-13 07:00:00"),  # 8h duration, 7h night (23:00 to 06:00)
        ]
    )

    night_hours = compute_night_hours_vectorized(punch_ins, punch_outs)

    assert night_hours.iloc[0] == 0.0
    assert night_hours.iloc[1] == 7.75
    assert night_hours.iloc[2] == 2.0
    assert night_hours.iloc[3] == 8.0
    assert night_hours.iloc[4] == 7.0


def test_compute_holiday_hours_vectorized_exactness() -> None:
    """Validate 0% error on holiday shifts and midnight transitions."""
    holidays = [date(2026, 1, 1), date(2026, 1, 6)]

    punch_ins = pd.Series(
        [
            pd.Timestamp("2026-01-01 08:00:00"),  # Full holiday shift
            pd.Timestamp("2026-01-05 20:00:00"),  # Starts normal, enters holiday at 00:00
            pd.Timestamp("2026-01-06 20:00:00"),  # Starts holiday, leaves holiday at 00:00
            pd.Timestamp("2026-01-10 08:00:00"),  # Regular workday
        ]
    )
    punch_outs = pd.Series(
        [
            pd.Timestamp("2026-01-01 16:00:00"),  # 8h holiday
            pd.Timestamp("2026-01-06 04:00:00"),  # 4h holiday (00:00 to 04:00)
            pd.Timestamp("2026-01-07 04:00:00"),  # 4h holiday (20:00 to 00:00)
            pd.Timestamp("2026-01-10 16:00:00"),  # 0h holiday
        ]
    )

    holiday_hours = compute_holiday_hours_vectorized(punch_ins, punch_outs, holidays)

    assert holiday_hours.iloc[0] == 8.0
    assert holiday_hours.iloc[1] == 4.0
    assert holiday_hours.iloc[2] == 4.0
    assert holiday_hours.iloc[3] == 0.0


def test_compute_labor_distribution_vectorized() -> None:
    """Validate ordinary vs excess hours split."""
    total_hours = pd.Series([6.0, 8.0, 9.5, 10.0])
    ordinary, excess = compute_labor_distribution_vectorized(
        total_hours, theoretical_daily_hours=8.0
    )

    assert ordinary.tolist() == [6.0, 8.0, 8.0, 8.0]
    assert excess.tolist() == [0.0, 0.0, 1.5, 2.0]


def test_reconcile_attendance_events_card_bounce_and_incidents() -> None:
    """Validate card bounce deduplication and incident tagging for orphan punches."""
    # Data with card bounce on IN and orphan punches
    df = pd.DataFrame(
        {
            "employee_code": ["EMP1", "EMP1", "EMP1", "EMP2", "EMP3"],
            "timestamp": [
                pd.Timestamp("2026-01-15 08:00:00"),
                pd.Timestamp("2026-01-15 08:00:10"),  # Bounce! (10s later)
                pd.Timestamp("2026-01-15 16:00:00"),  # OUT
                pd.Timestamp("2026-01-15 08:00:00"),  # Orphan IN (no exit)
                pd.Timestamp("2026-01-15 16:00:00"),  # Orphan OUT (no entry)
            ],
            "event_type": pd.Categorical(
                ["IN", "IN", "OUT", "IN", "OUT"], categories=["IN", "OUT"]
            ),
            "source_row": [2, 3, 4, 5, 6],
        }
    )

    reconciled = reconcile_attendance_events(df)

    # 1 valid pair for EMP1, 1 incident for EMP2, 1 incident for EMP3 -> Total 3 records
    assert len(reconciled) == 3

    emp1_rec = reconciled[reconciled["employee_code"] == "EMP1"].iloc[0]
    assert not emp1_rec["has_incident"]
    assert emp1_rec["total_hours"] == 8.0

    emp2_rec = reconciled[reconciled["employee_code"] == "EMP2"].iloc[0]
    assert emp2_rec["has_incident"]
    assert emp2_rec["incident_type"] == "MISSING_EXIT"

    emp3_rec = reconciled[reconciled["employee_code"] == "EMP3"].iloc[0]
    assert emp3_rec["has_incident"]
    assert emp3_rec["incident_type"] == "ORPHAN_EXIT"


def test_reconciliation_benchmark_5000_records() -> None:
    """Benchmark: Processing 5,000 synthetic records must take under 3.0 seconds in memory."""
    # 1. Generate 5,000 synthetic records
    csv_str = generate_synthetic_csv(num_records=5000)

    # 2. Normalize CSV into canonical DataFrame
    t1 = time.perf_counter()
    canonical_df = normalize_attendance_file(BytesIO(csv_str.encode("utf-8")), "csv")
    norm_time = time.perf_counter() - t1

    assert len(canonical_df) == 5000

    # 3. Vectorized reconciliation
    t2 = time.perf_counter()
    reconciled_df = reconcile_attendance_events(
        canonical_df,
        holiday_dates=SYNTHETIC_HOLIDAYS,
        theoretical_daily_hours=8.0,
    )
    recon_time = time.perf_counter() - t2

    total_processing_time = norm_time + recon_time

    # Assert correctness
    assert not reconciled_df.empty
    assert "ordinary_hours" in reconciled_df.columns
    assert "night_hours" in reconciled_df.columns
    assert "holiday_hours" in reconciled_df.columns

    # Performance requirement: Total processing (normalization + reconciliation) < 3.0 seconds
    assert total_processing_time < 3.0, (
        f"Processing exceeded 3.0s benchmark: {total_processing_time:.3f}s "
        f"(normalization: {norm_time:.3f}s, reconciliation: {recon_time:.3f}s)"
    )
