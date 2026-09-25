from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from chores.models import (
    Chore,
    ChoreAssignment,
    ChoreRotationMember,
    Household,
    HouseholdMembership,
)
from chores.services.rotation import initialize_chore_rotation


class ChoreRotationInitializationTests(TestCase):
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

    def test_initializes_ordered_rotation_and_pending_assignment_to_first_member(self):
        chore = Chore.objects.create(household=self.household, title='Clean kitchen')
        due_date = date(2026, 10, 3)

        assignment = initialize_chore_rotation(chore, due_date)

        rotations = list(chore.rotation_members.select_related('membership').all())
        self.assertEqual(
            [(item.membership_id, item.sequence_order) for item in rotations],
            [(self.admin_membership.pk, 0), (self.member_membership.pk, 1)],
        )
        self.assertEqual(assignment.chore, chore)
        self.assertEqual(assignment.assigned_to, rotations[0].membership)
        self.assertEqual(assignment.due_date, due_date)
        self.assertEqual(assignment.status, ChoreAssignment.Status.PENDING)
        self.assertIsNone(assignment.completed_at)
        self.assertIsNone(assignment.completed_by_id)

    def test_admin_is_included_even_when_not_already_a_membership(self):
        self.admin_membership.delete()
        chore = Chore.objects.create(household=self.household, title='Take bins out')

        assignment = initialize_chore_rotation(chore, date(2026, 10, 3))

        admin_membership = HouseholdMembership.objects.get(
            user=self.admin,
            household=self.household,
        )
        self.assertTrue(admin_membership.is_admin)
        self.assertTrue(ChoreRotationMember.objects.filter(
            chore=chore, membership=admin_membership,
        ).exists())
        self.assertEqual(chore.rotation_members.count(), 2)
        self.assertEqual(assignment.status, ChoreAssignment.Status.PENDING)

    def test_single_member_household_assigns_admin_at_sequence_zero(self):
        self.member_membership.delete()
        chore = Chore.objects.create(household=self.household, title='Water plants')

        assignment = initialize_chore_rotation(chore, date(2026, 10, 3))

        self.assertEqual(chore.rotation_members.count(), 1)
        rotation = chore.rotation_members.get()
        self.assertEqual(rotation.membership, self.admin_membership)
        self.assertEqual(rotation.sequence_order, 0)
        self.assertEqual(assignment.assigned_to, self.admin_membership)

    def test_reinitialization_returns_existing_assignment_without_resetting_it(self):
        chore = Chore.objects.create(household=self.household, title='Clean kitchen')
        due_date = date(2026, 10, 3)
        first = initialize_chore_rotation(chore, due_date)
        first.status = ChoreAssignment.Status.OVERDUE
        first.save(update_fields=['status'])

        retry = initialize_chore_rotation(chore, date(2026, 11, 1))

        self.assertEqual(retry.pk, first.pk)
        self.assertEqual(retry.due_date, due_date)
        self.assertEqual(retry.status, ChoreAssignment.Status.OVERDUE)
        self.assertEqual(ChoreAssignment.objects.filter(chore=chore).count(), 1)

    def test_chore_creation_view_seeds_rotation_and_initial_assignment(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse('chore_create'), {
            'title': 'Wash dishes',
            'description': '',
            'frequency_type': Chore.FrequencyType.DAILY,
            'frequency_interval': '1',
            'is_active': 'on',
        })

        self.assertRedirects(response, reverse('chore_list'))
        chore = Chore.objects.get(title='Wash dishes')
        assignment = ChoreAssignment.objects.get(chore=chore)
        self.assertEqual(chore.rotation_members.count(), 2)
        self.assertEqual(assignment.assigned_to, self.admin_membership)
        self.assertEqual(assignment.status, ChoreAssignment.Status.PENDING)
        self.assertEqual(assignment.due_date, timezone.localdate())
