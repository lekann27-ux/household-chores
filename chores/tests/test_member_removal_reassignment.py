from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from chores.models import (
    Chore,
    ChoreAssignment,
    ChoreRotationMember,
    Household,
    HouseholdMembership,
)
from chores.services.members import remove_member_from_household
from chores.services.rotation import initialize_chore_rotation


class MemberRemovalReassignmentTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.member_to_remove = User.objects.create_user(username='remove-me', password='pass')
        self.next_member = User.objects.create_user(username='next-member', password='pass')
        self.household = Household.objects.create(name='Home', admin=self.admin)
        self.admin_membership = HouseholdMembership.objects.create(
            user=self.admin, household=self.household, is_admin=True,
        )
        self.removed_membership = HouseholdMembership.objects.create(
            user=self.member_to_remove, household=self.household,
        )
        self.next_membership = HouseholdMembership.objects.create(
            user=self.next_member, household=self.household,
        )
        self.kitchen = Chore.objects.create(household=self.household, title='Kitchen')
        self.kitchen_assignment = initialize_chore_rotation(self.kitchen, date(2026, 1, 5))
        self.kitchen_assignment.assigned_to = self.removed_membership
        self.kitchen_assignment.save(update_fields=['assigned_to'])

        self.bathroom = Chore.objects.create(household=self.household, title='Bathroom')
        self.bathroom_assignment = ChoreAssignment.objects.create(
            chore=self.bathroom,
            assigned_to=self.removed_membership,
            due_date=date(2026, 1, 7),
            status=ChoreAssignment.Status.OVERDUE,
        )
        ChoreRotationMember.objects.create(
            chore=self.bathroom,
            membership=self.next_membership,
            sequence_order=0,
        )
        ChoreRotationMember.objects.create(
            chore=self.bathroom,
            membership=self.admin_membership,
            sequence_order=1,
        )
        ChoreRotationMember.objects.create(
            chore=self.bathroom,
            membership=self.removed_membership,
            sequence_order=2,
        )

    def test_removal_reassigns_pending_and_overdue_to_next_rotation_member(self):
        reassigned = remove_member_from_household(self.removed_membership, self.admin)

        self.assertEqual(reassigned, 2)
        self.kitchen_assignment.refresh_from_db()
        self.bathroom_assignment.refresh_from_db()
        self.assertEqual(self.kitchen_assignment.assigned_to, self.next_membership)
        self.assertEqual(self.kitchen_assignment.status, ChoreAssignment.Status.PENDING)
        self.assertEqual(self.kitchen_assignment.due_date, date(2026, 1, 5))
        self.assertEqual(self.bathroom_assignment.assigned_to, self.next_membership)
        self.assertEqual(self.bathroom_assignment.status, ChoreAssignment.Status.OVERDUE)
        self.assertEqual(self.bathroom_assignment.due_date, date(2026, 1, 7))

    def test_removal_drops_member_and_reindexes_every_household_rotation(self):
        remove_member_from_household(self.removed_membership, self.admin)

        self.assertFalse(HouseholdMembership.objects.filter(pk=self.removed_membership.pk).exists())
        for chore in (self.kitchen, self.bathroom):
            orders = list(chore.rotation_members.order_by('sequence_order').values_list(
                'membership_id', 'sequence_order',
            ))
            self.assertNotIn(self.removed_membership.pk, [membership_id for membership_id, _ in orders])
            self.assertEqual([order for _, order in orders], list(range(len(orders))))

    def test_removal_does_not_change_unrelated_household(self):
        other_admin = User.objects.create_user(username='other-admin', password='pass')
        other_member = User.objects.create_user(username='other-member', password='pass')
        other_household = Household.objects.create(name='Other Home', admin=other_admin)
        other_admin_membership = HouseholdMembership.objects.create(
            user=other_admin, household=other_household, is_admin=True,
        )
        other_membership = HouseholdMembership.objects.create(
            user=other_member, household=other_household,
        )
        other_chore = Chore.objects.create(household=other_household, title='Other chore')
        other_rotation = ChoreRotationMember.objects.create(
            chore=other_chore,
            membership=other_membership,
            sequence_order=0,
        )
        other_assignment = ChoreAssignment.objects.create(
            chore=other_chore,
            assigned_to=other_membership,
            due_date=date(2026, 1, 8),
        )

        remove_member_from_household(self.removed_membership, self.admin)

        self.assertTrue(HouseholdMembership.objects.filter(pk=other_membership.pk).exists())
        other_rotation.refresh_from_db()
        other_assignment.refresh_from_db()
        self.assertEqual(other_rotation.sequence_order, 0)
        self.assertEqual(other_assignment.assigned_to, other_membership)
        self.assertTrue(HouseholdMembership.objects.filter(pk=other_admin_membership.pk).exists())

    def test_non_admin_cannot_remove_member_and_admin_cannot_remove_self(self):
        with self.assertRaises(PermissionDenied):
            remove_member_from_household(self.removed_membership, self.next_member)
        with self.assertRaises(ValidationError):
            remove_member_from_household(self.admin_membership, self.admin)

        self.assertTrue(HouseholdMembership.objects.filter(pk=self.removed_membership.pk).exists())
        self.assertTrue(HouseholdMembership.objects.filter(pk=self.admin_membership.pk).exists())

    def test_single_remaining_admin_takes_over_pending_work(self):
        self.next_membership.delete()

        remove_member_from_household(self.removed_membership, self.admin)

        self.kitchen_assignment.refresh_from_db()
        self.assertEqual(self.kitchen_assignment.assigned_to, self.admin_membership)
        self.assertEqual(self.kitchen.rotation_members.get().membership, self.admin_membership)
        self.assertEqual(self.kitchen.rotation_members.get().sequence_order, 0)

    def test_member_removal_view_runs_reassignment_service(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse(
            'household_remove_member', args=[self.removed_membership.pk],
        ))

        self.assertRedirects(response, reverse('household_members'))
        self.kitchen_assignment.refresh_from_db()
        self.assertEqual(self.kitchen_assignment.assigned_to, self.next_membership)
        self.assertFalse(HouseholdMembership.objects.filter(pk=self.removed_membership.pk).exists())
