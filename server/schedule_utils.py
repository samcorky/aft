"""Schedule calculation utilities for scheduled cards."""
from datetime import datetime, timedelta
from typing import List, Optional


def _add_months(dt: datetime, months: int) -> datetime:
    """Add months to a datetime (simple implementation)."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return dt.replace(year=year, month=month, day=day)


def _add_years(dt: datetime, years: int) -> datetime:
    """Add years to a datetime."""
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        # Handle leap year edge case (Feb 29)
        return dt.replace(year=dt.year + years, day=28)


def calculate_next_runs(
    run_every: int,
    unit: str,
    start_datetime: datetime,
    end_datetime: Optional[datetime] = None,
    max_results: int = 4
) -> List[str]:
    """Calculate the next N scheduled run times.
    
    Args:
        run_every: Interval value (e.g., 1, 2, 5)
        unit: Unit of time ('minute', 'hour', 'day', 'week', 'month', 'year')
        start_datetime: Schedule start datetime
        end_datetime: Optional schedule end datetime
        max_results: Maximum number of future run times to return
        
    Returns:
        List of ISO formatted datetime strings representing the next scheduled runs
    """
    now = datetime.now()
    current = start_datetime
    next_runs = []
    
    # If start is in the past, calculate the next occurrence after now
    if current < now:
        current = _calculate_next_occurrence_after(current, run_every, unit, now)
    
    # Generate up to max_results future run times
    for _ in range(max_results * 10):  # Safety limit to prevent infinite loops
        if len(next_runs) >= max_results:
            break
            
        # Check if current time is beyond end time
        if end_datetime and current > end_datetime:
            break
            
        # Only include times that are in the future
        if current >= now:
            next_runs.append(current.isoformat())
        
        # Calculate next occurrence
        current = _add_interval(current, run_every, unit)
        
    return next_runs


def get_next_run(start: datetime, after: datetime, run_every: int, unit: str) -> Optional[datetime]:
    """Calculate the next run time for a schedule after a given datetime.
    
    Args:
        start: The schedule start datetime
        after: Calculate next occurrence after this datetime
        run_every: Interval value
        unit: Unit of time
        
    Returns:
        The next scheduled datetime after 'after', or None if invalid
    """
    return _calculate_next_occurrence_after(start, run_every, unit, after)


def _calculate_next_occurrence_after(start: datetime, run_every: int, unit: str, after: datetime) -> datetime:
    """Calculate the next occurrence of a schedule after a given datetime.
    
    Args:
        start: The schedule start datetime
        run_every: Interval value
        unit: Unit of time
        after: Calculate next occurrence after this datetime
        
    Returns:
        The next scheduled datetime after 'after'
    """
    current = start
    
    # Calculate how many intervals have passed
    if unit == 'minute':
        delta_minutes = (after - start).total_seconds() / 60
        intervals_passed = int(delta_minutes / run_every)
        if delta_minutes % run_every != 0:
            intervals_passed += 1
        current = start + timedelta(minutes=run_every * intervals_passed)
        
    elif unit == 'hour':
        delta_hours = (after - start).total_seconds() / 3600
        intervals_passed = int(delta_hours / run_every)
        if delta_hours % run_every != 0:
            intervals_passed += 1
        current = start + timedelta(hours=run_every * intervals_passed)
        
    elif unit == 'day':
        delta_days = (after.date() - start.date()).days
        intervals_passed = int(delta_days / run_every)
        if delta_days % run_every != 0:
            intervals_passed += 1
        current = start + timedelta(days=run_every * intervals_passed)
        
    elif unit == 'week':
        delta_days = (after.date() - start.date()).days
        delta_weeks = delta_days / 7
        intervals_passed = int(delta_weeks / run_every)
        if delta_weeks % run_every != 0:
            intervals_passed += 1
        current = start + timedelta(weeks=run_every * intervals_passed)
        
    elif unit == 'month':
        months_diff = (after.year - start.year) * 12 + (after.month - start.month)
        intervals_passed = int(months_diff / run_every)
        if months_diff % run_every != 0 or after.day > start.day:
            intervals_passed += 1
        current = _add_months(start, run_every * intervals_passed)
        
    elif unit == 'year':
        years_diff = after.year - start.year
        intervals_passed = int(years_diff / run_every)
        if years_diff % run_every != 0 or (after.month, after.day) > (start.month, start.day):
            intervals_passed += 1
        current = _add_years(start, run_every * intervals_passed)
    
    return current


def _add_interval(dt: datetime, run_every: int, unit: str) -> datetime:
    """Add an interval to a datetime.
    
    Args:
        dt: The datetime to add to
        run_every: Interval value
        unit: Unit of time
        
    Returns:
        New datetime with interval added
    """
    if unit == 'minute':
        return dt + timedelta(minutes=run_every)
    elif unit == 'hour':
        return dt + timedelta(hours=run_every)
    elif unit == 'day':
        return dt + timedelta(days=run_every)
    elif unit == 'week':
        return dt + timedelta(weeks=run_every)
    elif unit == 'month':
        return _add_months(dt, run_every)
    elif unit == 'year':
        return _add_years(dt, run_every)
    else:
        raise ValueError(f"Invalid unit: {unit}")


def should_create_card(
    run_every: int,
    unit: str,
    start_datetime: datetime,
    end_datetime: Optional[datetime],
    now: Optional[datetime] = None
) -> bool:
    """Determine if a card should be created at the current time.
    
    Args:
        run_every: Interval value
        unit: Unit of time
        start_datetime: Schedule start datetime
        end_datetime: Optional schedule end datetime
        now: Current datetime (defaults to datetime.now())
        
    Returns:
        True if a card should be created, False otherwise
    """
    if now is None:
        now = datetime.now()
    
    # Not yet started
    if now < start_datetime:
        return False
    
    # Check if past end time
    if end_datetime and now > end_datetime:
        return False
    
    # Calculate if current time aligns with schedule
    next_occurrence = _calculate_next_occurrence_after(start_datetime, run_every, unit, now)
    
    # Check if we're within the same minute as the next occurrence
    # (scheduler runs every minute, so we have a 1-minute window)
    time_diff = abs((next_occurrence - now).total_seconds())
    return time_diff < 60  # Within 60 seconds
