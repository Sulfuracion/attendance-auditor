"""Vectorized labor calculations for hours, nocturnal shifts, and holiday surcharges.

Enforces zero-loop Pandas / NumPy vectorization for high-throughput reconciliation.
"""

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd


def compute_night_hours_vectorized(
    punch_in: pd.Series,
    punch_out: pd.Series,
) -> pd.Series:
    """Compute exact night hours (overlap with [22:00, 06:00]) vectorially.

    Handles midnight crossings seamlessly by evaluating two distinct night windows:
    - Window A (Day D early morning): [D 00:00, D 06:00]
    - Window B (Day D evening to Day D+1 morning): [D 22:00, D+1 06:00]

    Args:
        punch_in: Series of timestamp start times (datetime64[ns]).
        punch_out: Series of timestamp end times (datetime64[ns]).

    Returns:
        Series of nocturnal hours as float.
    """
    if punch_in.empty:
        return pd.Series(dtype=float)

    # Base day floor
    day_start = punch_in.dt.floor("D")

    # Window A: [D 00:00, D 06:00]
    win_a_start = day_start
    win_a_end = day_start + np.timedelta64(6, "h")

    overlap_a_start = np.maximum(punch_in.values, win_a_start.values)
    overlap_a_end = np.minimum(punch_out.values, win_a_end.values)
    duration_a_ns = np.maximum(
        0, (overlap_a_end - overlap_a_start).astype("timedelta64[ns]").astype(np.int64)
    )

    # Window B: [D 22:00, D+1 06:00] (Continuous 8-hour night window crossing midnight)
    win_b_start = day_start + np.timedelta64(22, "h")
    win_b_end = day_start + np.timedelta64(30, "h")  # Next day 06:00

    overlap_b_start = np.maximum(punch_in.values, win_b_start.values)
    overlap_b_end = np.minimum(punch_out.values, win_b_end.values)
    duration_b_ns = np.maximum(
        0, (overlap_b_end - overlap_b_start).astype("timedelta64[ns]").astype(np.int64)
    )

    # Convert nanoseconds to hours (1 hour = 3.6e12 ns)
    total_night_hours = (duration_a_ns + duration_b_ns) / 3_600_000_000_000.0
    return pd.Series(np.round(total_night_hours, 4), index=punch_in.index)


def compute_holiday_hours_vectorized(
    punch_in: pd.Series,
    punch_out: pd.Series,
    holiday_dates: Sequence[date] | pd.DatetimeIndex,
) -> pd.Series:
    """Compute hours falling on official holidays or weekends vectorially.

    Accounts for shifts beginning on a normal day and crossing midnight into a holiday,
    or starting on a holiday and crossing into a normal working day.

    Args:
        punch_in: Series of timestamp start times (datetime64[ns]).
        punch_out: Series of timestamp end times (datetime64[ns]).
        holiday_dates: List or DatetimeIndex of holiday dates.

    Returns:
        Series of holiday hours as float.
    """
    if punch_in.empty:
        return pd.Series(dtype=float)

    day1 = punch_in.dt.floor("D")
    day2 = day1 + np.timedelta64(1, "D")

    # Convert holiday dates to DatetimeIndex normalized to midnight
    holidays_idx = pd.to_datetime(list(holiday_dates)).floor("D")

    # Boolean masks for holiday days
    is_day1_holiday = day1.isin(holidays_idx).values
    is_day2_holiday = day2.isin(holidays_idx).values

    # Portion belonging to Day 1: [punch_in, min(punch_out, day2)]
    d1_end = np.minimum(punch_out.values, day2.values)
    d1_dur_ns = np.maximum(0, (d1_end - punch_in.values).astype("timedelta64[ns]").astype(np.int64))

    # Portion belonging to Day 2: [max(punch_in, day2), punch_out]
    d2_start = np.maximum(punch_in.values, day2.values)
    d2_dur_ns = np.maximum(
        0, (punch_out.values - d2_start).astype("timedelta64[ns]").astype(np.int64)
    )

    # Calculate hours
    d1_hours = np.where(is_day1_holiday, d1_dur_ns / 3_600_000_000_000.0, 0.0)
    d2_hours = np.where(is_day2_holiday, d2_dur_ns / 3_600_000_000_000.0, 0.0)

    total_holiday_hours = np.round(d1_hours + d2_hours, 4)
    return pd.Series(total_holiday_hours, index=punch_in.index)


def compute_labor_distribution_vectorized(
    total_hours: pd.Series,
    theoretical_daily_hours: float = 8.0,
) -> tuple[pd.Series, pd.Series]:
    """Split total hours into ordinary hours and excess hours vectorially.

    Args:
        total_hours: Series of total worked hours.
        theoretical_daily_hours: Standard daily limit before excess hours trigger.

    Returns:
        Tuple of (ordinary_hours, excess_hours).
    """
    ordinary = np.minimum(total_hours.values, theoretical_daily_hours)
    excess = np.maximum(0.0, total_hours.values - theoretical_daily_hours)

    return (
        pd.Series(np.round(ordinary, 4), index=total_hours.index),
        pd.Series(np.round(excess, 4), index=total_hours.index),
    )
