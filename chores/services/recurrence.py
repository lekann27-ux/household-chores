"""Pure calendar-date recurrence calculations for chores."""

import calendar
from datetime import date, datetime, timedelta

from chores.models import Chore


def calculate_next_due_date(frequency_type, frequency_interval, base_date):
    """Return the next scheduled date using a date-only recurrence interval.

    Monthly dates clamp to the last day of the target month when the original
    day does not exist there (for example, January 31 becomes February 28).
    """
    if isinstance(base_date, datetime) or not isinstance(base_date, date):
        raise TypeError('base_date must be a datetime.date, not a datetime.')
    if not isinstance(frequency_interval, int) or isinstance(frequency_interval, bool):
        raise TypeError('frequency_interval must be an integer.')
    if frequency_interval < 1:
        raise ValueError('frequency_interval must be at least 1.')

    if frequency_type in (Chore.FrequencyType.DAILY, Chore.FrequencyType.INTERVAL_DAYS):
        return base_date + timedelta(days=frequency_interval)
    if frequency_type == Chore.FrequencyType.WEEKLY:
        return base_date + timedelta(weeks=frequency_interval)
    if frequency_type == Chore.FrequencyType.MONTHLY:
        month_index = base_date.year * 12 + base_date.month - 1 + frequency_interval
        year, month_offset = divmod(month_index, 12)
        month = month_offset + 1
        day = min(base_date.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    raise ValueError(f'Unsupported frequency type: {frequency_type!r}')
