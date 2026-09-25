from datetime import date, datetime

from django.test import SimpleTestCase

from chores.models import Chore
from chores.services.recurrence import calculate_next_due_date


class RecurrenceTests(SimpleTestCase):
    def test_daily_uses_interval_days(self):
        self.assertEqual(
            calculate_next_due_date(Chore.FrequencyType.DAILY, 1, date(2026, 4, 2)),
            date(2026, 4, 3),
        )

    def test_interval_days_supports_multiple_days(self):
        self.assertEqual(
            calculate_next_due_date(Chore.FrequencyType.INTERVAL_DAYS, 4, date(2026, 4, 2)),
            date(2026, 4, 6),
        )

    def test_weekly_and_biweekly_intervals(self):
        base = date(2026, 4, 2)
        self.assertEqual(
            calculate_next_due_date(Chore.FrequencyType.WEEKLY, 1, base),
            date(2026, 4, 9),
        )
        self.assertEqual(
            calculate_next_due_date(Chore.FrequencyType.WEEKLY, 2, base),
            date(2026, 4, 16),
        )

    def test_monthly_clamps_end_of_month_and_preserves_day_when_possible(self):
        self.assertEqual(
            calculate_next_due_date(Chore.FrequencyType.MONTHLY, 1, date(2025, 1, 31)),
            date(2025, 2, 28),
        )
        self.assertEqual(
            calculate_next_due_date(Chore.FrequencyType.MONTHLY, 1, date(2024, 1, 31)),
            date(2024, 2, 29),
        )
        self.assertEqual(
            calculate_next_due_date(Chore.FrequencyType.MONTHLY, 1, date(2025, 3, 30)),
            date(2025, 4, 30),
        )
        self.assertEqual(
            calculate_next_due_date(Chore.FrequencyType.MONTHLY, 2, date(2025, 1, 31)),
            date(2025, 3, 31),
        )

    def test_invalid_frequency_and_interval_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_next_due_date('YEARLY', 1, date(2026, 1, 1))
        with self.assertRaises(ValueError):
            calculate_next_due_date(Chore.FrequencyType.DAILY, 0, date(2026, 1, 1))

    def test_datetime_is_rejected_to_preserve_date_only_semantics(self):
        with self.assertRaises(TypeError):
            calculate_next_due_date(
                Chore.FrequencyType.DAILY, 1, datetime(2026, 1, 1, 12, 0),
            )
