"""Vectorized attendance reconciliation engine.

Reconciles raw event streams into paired shifts and flagged incidents
using NumPy boolean masks and Series.shift().
PROHIBITED: iterrows(), itertuples(), and row-level Python for loops.
"""

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd

from src.core.rules.shifts import (
    compute_holiday_hours_vectorized,
    compute_labor_distribution_vectorized,
    compute_night_hours_vectorized,
)


def reconcile_attendance_events(
    df: pd.DataFrame,
    holiday_dates: Sequence[date] | pd.DatetimeIndex = (),
    theoretical_daily_hours: float = 8.0,
    bounce_threshold_seconds: float = 30.0,
) -> pd.DataFrame:
    """Reconcile normalized attendance event streams into worked shifts and incident records.

    Vectorized Algorithm:
    1. Filter out card bounces (consecutive identical events within bounce_threshold_seconds).
    2. Vectorized IN/OUT pair detection using Series.shift(-1) and equality masks.
    3. Calculate total duration, night hours, holiday hours, and excess hours vectorially.
    4. Flag unpaired events (orphan IN or orphan OUT) as incidents without halting execution.

    Args:
        df: Canonical DataFrame with columns:
            ['employee_code', 'timestamp', 'event_type', 'source_row'].
        holiday_dates: Official holiday calendar dates.
        theoretical_daily_hours: Standard daily shift hours (default 8.0).
        bounce_threshold_seconds: Minimum time between duplicate punches to ignore bounce.

    Returns:
        Consolidated DataFrame of reconciled shifts and incidents.
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "employee_code",
                "date",
                "punch_in",
                "punch_out",
                "total_hours",
                "ordinary_hours",
                "night_hours",
                "holiday_hours",
                "excess_hours",
                "has_incident",
                "incident_type",
                "source_rows",
            ]
        )

    # Work on a copy sorted strictly by employee_code and timestamp
    working_df = df.sort_values(
        by=["employee_code", "timestamp"], ascending=[True, True]
    ).reset_index(drop=True)

    # 1. Filter out immediate duplicate card bounces (same emp, same event, within threshold)
    is_same_emp = working_df["employee_code"].values == working_df["employee_code"].shift(1).values
    is_same_event = working_df["event_type"].values == working_df["event_type"].shift(1).values
    time_diff_sec = (
        (working_df["timestamp"] - working_df["timestamp"].shift(1))
        .dt.total_seconds()
        .fillna(999999.0)
        .values
    )
    is_bounce = is_same_emp & is_same_event & (time_diff_sec < bounce_threshold_seconds)
    working_df = working_df[~is_bounce].reset_index(drop=True)

    # 2. Vectorized IN/OUT pair matching
    curr_event = working_df["event_type"].values
    curr_emp = working_df["employee_code"].values
    curr_time = working_df["timestamp"].values

    next_event = working_df["event_type"].shift(-1).values
    next_emp = working_df["employee_code"].shift(-1).values
    next_time = working_df["timestamp"].shift(-1).values

    # Valid IN condition: current is IN, next is OUT, same employee, and next_time > curr_time
    is_valid_in = (
        (curr_event == "IN")
        & (next_event == "OUT")
        & (curr_emp == next_emp)
        & (next_time > curr_time)
    )

    # The matching OUT for each valid IN is at the subsequent index
    is_valid_out = np.zeros(len(working_df), dtype=bool)
    is_valid_out[1:] = is_valid_in[:-1]

    # Partition into paired shifts and unpaired anomaly events
    paired_in_df = working_df[is_valid_in].reset_index(drop=True)
    paired_out_df = working_df[is_valid_out].reset_index(drop=True)

    # Extract unpaired rows (incidents)
    is_unpaired = ~(is_valid_in | is_valid_out)
    unpaired_df = working_df[is_unpaired].reset_index(drop=True)

    # 3. Process Paired Shifts (Vectorized calculations)
    if not paired_in_df.empty:
        paired_punch_in = paired_in_df["timestamp"]
        paired_punch_out = paired_out_df["timestamp"]
        paired_emp = paired_in_df["employee_code"]

        # Duration in hours
        duration_ns = (
            (paired_punch_out.values - paired_punch_in.values)
            .astype("timedelta64[ns]")
            .astype(np.int64)
        )
        total_hours = pd.Series(
            np.round(duration_ns / 3_600_000_000_000.0, 4),
            index=paired_in_df.index,
        )

        # Vectorized night hours [22:00, 06:00]
        night_hours = compute_night_hours_vectorized(paired_punch_in, paired_punch_out)

        # Vectorized holiday hours
        holiday_hours = compute_holiday_hours_vectorized(
            paired_punch_in, paired_punch_out, holiday_dates
        )

        # Vectorized ordinary and excess hours
        ordinary_hours, excess_hours = compute_labor_distribution_vectorized(
            total_hours, theoretical_daily_hours=theoretical_daily_hours
        )

        # Source rows trace
        source_rows = (
            paired_in_df["source_row"].astype(str) + "," + paired_out_df["source_row"].astype(str)
        )

        reconciled_pairs = pd.DataFrame(
            {
                "employee_code": paired_emp,
                "date": paired_punch_in.dt.date,
                "punch_in": paired_punch_in,
                "punch_out": paired_punch_out,
                "total_hours": total_hours,
                "ordinary_hours": ordinary_hours,
                "night_hours": night_hours,
                "holiday_hours": holiday_hours,
                "excess_hours": excess_hours,
                "has_incident": False,
                "incident_type": None,
                "source_rows": source_rows,
            }
        )
    else:
        reconciled_pairs = pd.DataFrame()

    # 4. Process Unpaired Events (Anomalies / Incidents)
    if not unpaired_df.empty:
        is_orphan_in = unpaired_df["event_type"].values == "IN"

        # Punch in / out assignments
        unpaired_punch_in = pd.Series(
            np.where(is_orphan_in, unpaired_df["timestamp"].values, np.datetime64("NaT", "ns")),
            index=unpaired_df.index,
            dtype="datetime64[ns]",
        )
        unpaired_punch_out = pd.Series(
            np.where(~is_orphan_in, unpaired_df["timestamp"].values, np.datetime64("NaT", "ns")),
            index=unpaired_df.index,
            dtype="datetime64[ns]",
        )
        incident_types = np.where(is_orphan_in, "MISSING_EXIT", "ORPHAN_EXIT")

        reconciled_incidents = pd.DataFrame(
            {
                "employee_code": unpaired_df["employee_code"],
                "date": unpaired_df["timestamp"].dt.date,
                "punch_in": unpaired_punch_in,
                "punch_out": unpaired_punch_out,
                "total_hours": 0.0,
                "ordinary_hours": 0.0,
                "night_hours": 0.0,
                "holiday_hours": 0.0,
                "excess_hours": 0.0,
                "has_incident": True,
                "incident_type": incident_types,
                "source_rows": unpaired_df["source_row"].astype(str),
            }
        )
    else:
        reconciled_incidents = pd.DataFrame()

    # 5. Concatenate and sort consolidated output
    results = pd.concat([reconciled_pairs, reconciled_incidents], ignore_index=True)
    results = results.sort_values(
        by=["employee_code", "date", "punch_in"],
        ascending=[True, True, True],
        na_position="last",
    ).reset_index(drop=True)

    return results
