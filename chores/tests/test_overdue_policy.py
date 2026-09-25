from datetime import date
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from chores.models import Chore, ChoreAssignment, Household, HouseholdMembership
from chores.services.assignments import mark_overdue_assignments
from chores.services.rotation import initialize_chore_rotation


class OverduePolicyTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.member = User.objects.create_user(username='member', password='pass')
        self.household = Household.objects.create(name='Home', admin=self.admin)
        self.admin_membership = HouseholdMembership.objects.create(
            user=self.admin, household=self.household, is_admin=True,
        )
        self.member_membership = HouseholdMembership.objects.create(
            user=self.member, household=self.household,
        )
        self.chore = Chore.objects.create(household=self.household, title='Clean kitchen')
        self.assignment = initialize_chore_rotation(self.chore, date(2026, 1, 1))

    def test_scanner_marks_only_pending_assignments_past_due(self):
        due_today_chore = Chore.objects.create(household=self.household, title='Due today')
        due_today = initialize_chore_rotation(due_today_chore, date(2026, 2, 10))
        completed_chore = Chore.objects.create(household=self.household, title='Completed')
        completed = initialize_chore_rotation(completed_chore, date(2026, 1, 1))
        completed.status = ChoreAssignment.Status.COMPLETED
        completed.save(update_fields=['status'])

        count = mark_overdue_assignments(date(2026, 2, 10))

        self.assertEqual(count, 1)
        self.assignment.refresh_from_db()
        due_today.refresh_from_db()
        completed.refresh_from_db()
        self.assertEqual(self.assignment.status, ChoreAssignment.Status.OVERDUE)
        self.assertEqual(due_today.status, ChoreAssignment.Status.PENDING)
        self.assertEqual(completed.status, ChoreAssignment.Status.COMPLETED)

    def test_overdue_assignment_stays_with_same_member_and_scanner_does_not_advance(self):
        assigned_to = self.assignment.assigned_to_id

        count = mark_overdue_assignments(date(2026, 2, 10))

        self.assignment.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(self.assignment.status, ChoreAssignment.Status.OVERDUE)
        self.assertEqual(self.assignment.assigned_to_id, assigned_to)
        self.assertEqual(ChoreAssignment.objects.filter(chore=self.chore).count(), 1)
        self.assertFalse(ChoreAssignment.objects.filter(
            chore=self.chore,
            assigned_to=self.member_membership,
        ).exists())

    def test_scanner_is_idempotent(self):
        self.assertEqual(mark_overdue_assignments(date(2026, 2, 10)), 1)
        self.assertEqual(mark_overdue_assignments(date(2026, 2, 10)), 0)

    @patch('chores.services.assignments.timezone.localdate', return_value=date(2026, 2, 10))
    def test_check_overdue_management_command_reports_processed_count(self, _today):
        output = StringIO()

        call_command('check_overdue_chores', stdout=output)

        self.assertIn('Marked 1 assignment(s) overdue.', output.getvalue())
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ChoreAssignment.Status.OVERDUE)

    def test_check_overdue_management_command_is_safe_to_run_repeatedly(self):
        output = StringIO()
        with patch('chores.services.assignments.timezone.localdate', return_value=date(2026, 2, 10)):
            call_command('check_overdue_chores', stdout=output)
            call_command('check_overdue_chores', stdout=output)

        self.assertIn('Marked 1 assignment(s) overdue.', output.getvalue())
        self.assertIn('Marked 0 assignment(s) overdue.', output.getvalue())
