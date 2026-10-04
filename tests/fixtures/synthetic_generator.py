"""Synthetic dataset generator for stress-testing and benchmarking attendance auditing.

Produces 5,000+ realistic attendance punch records including critical edge cases:
- Card bounces / duplicate punches within 10-30 seconds.
- Nocturnal shifts crossing midnight (e.g. 21:30 to 05:45).
- Holiday and weekend working shifts.
- Incomplete shifts (missing exit punch or orphan exit punch).
- Heterogeneous, mixed timestamp format representations.
"""

import random
from datetime import date, datetime, timedelta
from typing import Any

# Standard Spanish bank holidays for test scenarios
SYNTHETIC_HOLIDAYS: list[date] = [
    date(2026, 1, 1),  # New Year
    date(2026, 1, 6),  # Epiphany
    date(2026, 5, 1),  # Labor Day
    date(2026, 10, 12),  # National Day
    date(2026, 12, 25),  # Christmas
]


def format_mixed_timestamp(dt: datetime, format_choice: int) -> str:
    """Format a datetime object into one of several common heterogeneous formats."""
    if format_choice == 0:
        return dt.strftime("%Y-%m-%d %H:%M:%S")  # ISO 8601
    elif format_choice == 1:
        return dt.strftime("%d/%m/%Y %H:%M:%S")  # European standard
    elif format_choice == 2:
        return dt.strftime("%Y/%m/%d %H:%M")  # Slash date without seconds
    else:
        return dt.strftime("%d-%m-%Y %H:%M:%S")  # Hyphen European


def generate_synthetic_records(num_records: int = 5000, seed: int = 42) -> list[dict[str, Any]]:
    """Generate a list of synthetic attendance records with realistic edge cases."""
    rng = random.Random(seed)  # noqa: S311
    records: list[dict[str, Any]] = []

    employees = [f"EMP{i:03d}" for i in range(1, 51)]
    base_date = datetime(2026, 1, 1, 0, 0, 0)

    while len(records) < num_records:
        emp = rng.choice(employees)
        shift_type = rng.random()
        day_offset = rng.randint(0, 90)
        shift_day = base_date + timedelta(days=day_offset)

        # 1. Nocturnal shift crossing midnight (~20%)
        if shift_type < 0.20:
            in_hour = rng.randint(21, 23)
            in_minute = rng.choice([0, 15, 30, 45])
            punch_in = shift_day.replace(hour=in_hour, minute=in_minute, second=rng.randint(0, 59))
            duration_minutes = rng.randint(360, 510)  # 6 to 8.5 hours
            punch_out = punch_in + timedelta(minutes=duration_minutes)

            records.append(
                {
                    "codigo_empleado": emp,
                    "fecha_hora": format_mixed_timestamp(punch_in, rng.randint(0, 3)),
                    "tipo_evento": rng.choice(["IN", "ENTRADA", "E", "1"]),
                    "_sort_key": punch_in,
                }
            )
            records.append(
                {
                    "codigo_empleado": emp,
                    "fecha_hora": format_mixed_timestamp(punch_out, rng.randint(0, 3)),
                    "tipo_evento": rng.choice(["OUT", "SALIDA", "S", "0"]),
                    "_sort_key": punch_out,
                }
            )

        # 2. Incomplete shift / orphan punch (~10%)
        elif shift_type < 0.30:
            is_orphan_out = rng.choice([True, False])
            punch_time = shift_day.replace(
                hour=rng.randint(7, 20),
                minute=rng.randint(0, 59),
                second=rng.randint(0, 59),
            )
            event = (
                rng.choice(["OUT", "SALIDA", "S"])
                if is_orphan_out
                else rng.choice(["IN", "ENTRADA", "E"])
            )
            records.append(
                {
                    "codigo_empleado": emp,
                    "fecha_hora": format_mixed_timestamp(punch_time, rng.randint(0, 3)),
                    "tipo_evento": event,
                    "_sort_key": punch_time,
                }
            )

        # 3. Standard or Holiday regular day shift (~70%)
        else:
            in_hour = rng.randint(7, 9)
            in_minute = rng.randint(0, 45)
            punch_in = shift_day.replace(hour=in_hour, minute=in_minute, second=rng.randint(0, 59))
            duration_minutes = rng.randint(420, 540)  # 7 to 9 hours
            punch_out = punch_in + timedelta(minutes=duration_minutes)

            records.append(
                {
                    "codigo_empleado": emp,
                    "fecha_hora": format_mixed_timestamp(punch_in, rng.randint(0, 3)),
                    "tipo_evento": rng.choice(["IN", "ENTRADA", "E"]),
                    "_sort_key": punch_in,
                }
            )

            # Check if card bounce injection (~5% of shifts)
            if rng.random() < 0.05:
                bounce_time = punch_in + timedelta(seconds=rng.randint(2, 18))
                records.append(
                    {
                        "codigo_empleado": emp,
                        "fecha_hora": format_mixed_timestamp(bounce_time, rng.randint(0, 3)),
                        "tipo_evento": "IN",
                        "_sort_key": bounce_time,
                    }
                )

            records.append(
                {
                    "codigo_empleado": emp,
                    "fecha_hora": format_mixed_timestamp(punch_out, rng.randint(0, 3)),
                    "tipo_evento": rng.choice(["OUT", "SALIDA", "S"]),
                    "_sort_key": punch_out,
                }
            )

    # Slice to exact count
    records = records[:num_records]

    # Sort deterministically
    records.sort(key=lambda r: (r["codigo_empleado"], r["_sort_key"]))
    for r in records:
        del r["_sort_key"]

    return records


def generate_synthetic_csv(num_records: int = 5000, delimiter: str = ";") -> str:
    """Generate a raw CSV string representing the synthetic dataset."""
    records = generate_synthetic_records(num_records=num_records)
    header = f"codigo_empleado{delimiter}fecha_hora{delimiter}tipo_evento"
    lines = [header]
    for r in records:
        lines.append(
            f"{r['codigo_empleado']}{delimiter}{r['fecha_hora']}{delimiter}{r['tipo_evento']}"
        )
    return "\n".join(lines)
