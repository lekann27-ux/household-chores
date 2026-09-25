from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from chores.models import Chore, ChoreAssignment, Household, HouseholdMembership
from chores.services.assignments import complete_assignment
from chores.services.rotation import initialize_chore_rotation


class AssignmentCompletionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.member_one = User.objects.create_user(username='member-one', password='pass')
        self.member_two = User.objects.create_user(username='member-two', password='pass')
        self.household = Household.objects.create(name='Home', admin=self.admin)
        self.admin_membership = HouseholdMembership.objects.create(
            user=self.admin, household=self.household, is_admin=True,
        )
        self.member_one_membership = HouseholdMembership.objects.create(
            user=self.member_one, household=self.household,
        )
        self.member_two_membership = HouseholdMembership.objects.create(
            user=self.member_two, household=self.household,
        )
        self.chore = Chore.objects.create(
            household=self.household,
            title='Clean kitchen',
            frequency_type=Chore.FrequencyType.INTERVAL_DAYS,
            frequency_interval=2,
        )
        self.assignment = initialize_chore_rotation(self.chore, date(2026, 1, 1))

    @patch('chores.services.assignments.timezone.localdate', return_value=date(2026, 2, 10))
    def test_completion_records_actor_and_creates_next_assignment_by_recurrence(self, _today):
        assignment = complete_assignment(self.assignment.pk, self.admin_membership)

        self.assertEqual(assignment.status, ChoreAssignment.Status.COMPLETED)
        self.assertEqual(assignment.completed_by, self.admin_membership)
        self.assertIsNotNone(assignment.completed_at)
        next_assignment = ChoreAssignment.objects.get(
            chore=self.chore,
            status=ChoreAssignment.Status.PENDING,
        )
        self.assertEqual(next_assignment.assigned_to, self.member_one_membership)
        self.assertEqual(next_assignment.due_date, date(2026, 2, 12))

    @patch('chores.services.assignments.timezone.localdate', return_value=date(2026, 2, 10))
    def test_rotation_advances_in_order_and_wraps_to_admin(self, _today):
        first_next = complete_assignment(self.assignment.pk, self.admin_membership)
        second = ChoreAssignment.objects.get(status=ChoreAssignment.Status.PENDING)
        self.assertEqual(second.assigned_to, self.member_one_membership)

        complete_assignment(second.pk, self.member_one_membership)
        third = ChoreAssignment.objects.get(status=ChoreAssignment.Status.PENDING)
        self.assertEqual(third.assigned_to, self.member_two_membership)

        complete_assignment(third.pk, self.member_two_membership)
        wrapped = ChoreAssignment.objects.get(status=ChoreAssignment.Status.PENDING)
        self.assertEqual(wrapped.assigned_to, self.admin_membership)
        self.assertEqual(ChoreAssignment.objects.filter(chore=self.chore).count(), 4)
        self.assertEqual(first_next.pk, self.assignment.pk)

    @patch('chores.services.assignments.timezone.localdate', return_value=date(2026, 2, 10))
    def test_repeated_completion_is_idempotent(self, _today):
        first = complete_assignment(self.assignment.pk, self.admin_membership)
        completed_at = first.completed_at

        retry = complete_assignment(self.assignment.pk, self.admin_membership)

        self.assertEqual(retry.pk, first.pk)
        self.assertEqual(retry.completed_at, completed_at)
        self.assertEqual(ChoreAssignment.objects.filter(chore=self.chore).count(), 2)

    @patch('chores.services.assignments.timezone.localdate', return_value=date(2026, 2, 10))
    def test_overdue_completion_advances_from_completion_date(self, _today):
        self.assignment.status = ChoreAssignment.Status.OVERDUE
        self.assignment.save(update_fields=['status'])

        complete_assignment(self.assignment.pk, self.admin_membership)

        next_assignment = ChoreAssignment.objects.get(status=ChoreAssignment.Status.PENDING)
        self.assertEqual(next_assignment.due_date, date(2026, 2, 12))
        self.assertEqual(next_assignment.assigned_to, self.member_one_membership)

    def test_non_assignee_non_admin_cannot_complete(self):
        with self.assertRaises(PermissionDenied):
            complete_assignment(self.assignment.pk, self.member_one_membership)

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ChoreAssignment.Status.PENDING)
        self.assertEqual(ChoreAssignment.objects.filter(chore=self.chore).count(), 1)

    def test_inactive_chore_is_completed_without_creating_another_assignment(self):
        self.chore.is_active = False
        self.chore.save(update_fields=['is_active'])

        complete_assignment(self.assignment.pk, self.admin_membership)

        self.assertEqual(ChoreAssignment.objects.filter(chore=self.chore).count(), 1)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ChoreAssignment.Status.COMPLETED)

    def test_completion_endpoint_is_post_only_and_household_scoped(self):
        self.client.force_login(self.admin)
        url = reverse('complete_assignment', args=[self.assignment.pk])

        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertRedirects(response, reverse('chore_list'))
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ChoreAssignment.Status.COMPLETED)

        other_admin = User.objects.create_user(username='other-admin', password='pass')
        other_household = Household.objects.create(name='Other Home', admin=other_admin)
        HouseholdMembership.objects.create(
            user=other_admin, household=other_household, is_admin=True,
        )
        self.client.force_login(other_admin)
        self.assertEqual(self.client.post(url).status_code, 404)
