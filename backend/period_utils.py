"""Period utilities — Month / Quarter / Year / YTD."""
from datetime import datetime, timezone
from typing import List, Optional, Tuple


def parse_period(period_type: str, period_value: Optional[str]) -> Tuple[List[str], str]:
    """Return (list_of_YYYY-MM, display_label).

    period_type in { 'month', 'quarter', 'year', 'ytd', 'all' }
    period_value formats:
      month:   'YYYY-MM'
      quarter: 'YYYY-Q1' | 'YYYY-Q2' | ...
      year:    'YYYY'
      ytd:     'YYYY' (Jan..current month)
      all:     ignored
    """
    if period_type == "all":
        return [], "All periods"
    if not period_value:
        raise ValueError("period_value required")

    if period_type == "month":
        return [period_value], period_value

    if period_type == "year":
        y = int(period_value)
        return [f"{y}-{m:02d}" for m in range(1, 13)], f"FY {y}"

    if period_type == "quarter":
        y, q = period_value.split("-Q")
        qi = int(q)
        start_m = (qi - 1) * 3 + 1
        months = [f"{int(y)}-{m:02d}" for m in range(start_m, start_m + 3)]
        return months, f"Q{qi} {y}"

    if period_type == "ytd":
        y = int(period_value)
        # If current year, use current month; else use full year
        now = datetime.now(timezone.utc)
        end_m = now.month if now.year == y else 12
        return [f"{y}-{m:02d}" for m in range(1, end_m + 1)], f"YTD {y}"

    raise ValueError(f"Unknown period_type: {period_type}")


def month_query(period_type: str, period_value: Optional[str]) -> dict:
    """Return a MongoDB filter fragment matching the requested period on `report_month`.

    If period_type is 'all' OR period_value is missing/empty, returns {} (no filter).
    This lets the caller "start empty" until a period is picked without 500-ing.
    """
    if period_type == "all" or not period_value:
        return {}
    months, _ = parse_period(period_type, period_value)
    if not months:
        return {}
    if len(months) == 1:
        return {"report_month": months[0]}
    return {"report_month": {"$in": months}}
