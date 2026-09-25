from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from chores.models import (
    Chore,
    ChoreAssignment,
    ChoreRotationMember,
    Household,
    HouseholdMembership,
)
from chores.services.rotation import (
    enroll_member_in_active_chore_rotations,
    initialize_chore_rotation,
)


class MemberRotationOnboardingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.old_member = User.objects.create_user(username='old-member', password='pass')
        self.new_member = User.objects.create_user(username='new-member', password='pass')
        self.household = Household.objects.create(name='Home', admin=self.admin)
        self.admin_membership = HouseholdMembership.objects.create(
            user=self.admin, household=self.household, is_admin=True,
        )
        self.old_membership = HouseholdMembership.objects.create(
            user=self.old_member, household=self.household,
        )
        self.chore_one = Chore.objects.create(household=self.household, title='Kitchen')
        self.chore_two = Chore.objects.create(household=self.household, title='Bathroom')
        self.inactive_chore = Chore.objects.create(
            household=self.household, title='Inactive chore', is_active=False,
        )
        self.assignment_one = initialize_chore_rotation(self.chore_one, date(2026, 10, 3))
        self.assignment_two = initialize_chore_rotation(self.chore_two, date(2026, 10, 5))
        self.assignment_one.status = ChoreAssignment.Status.OVERDUE
        self.assignment_one.save(update_fields=['status'])
        ChoreRotationMember.objects.create(
            chore=self.inactive_chore,
            membership=self.admin_membership,
            sequence_order=0,
        )

    def test_join_via_code_appends_member_to_each_active_rotation(self):
        self.client.force_login(self.new_member)

        response = self.client.post(reverse('household_join'), {
            'join_code': self.household.join_code.lower(),
        })

        self.assertRedirects(response, reverse('household_members'))
        membership = HouseholdMembership.objects.get(
            user=self.new_member,
            household=self.household,
        )
        for chore in (self.chore_one, self.chore_two):
            rotation = ChoreRotationMember.objects.get(chore=chore, membership=membership)
            self.assertEqual(rotation.sequence_order, 2)
        self.assertFalse(ChoreRotationMember.objects.filter(
            chore=self.inactive_chore,
            membership=membership,
        ).exists())

    def test_join_preserves_existing_rotation_order_and_assignment_state(self):
        before_orders = {
            chore.pk: list(chore.rotation_members.values_list(
                'membership_id', 'sequence_order',
            ))
            for chore in (self.chore_one, self.chore_two)
        }
        before_assignments = {
            assignment.pk: (assignment.assigned_to_id, assignment.due_date, assignment.status)
            for assignment in (self.assignment_one, self.assignment_two)
        }
        self.client.force_login(self.new_member)

        self.client.post(reverse('household_join'), {'join_code': self.household.join_code})

        for chore in (self.chore_one, self.chore_two):
            old_orders = list(chore.rotation_members.exclude(
                membership__user=self.new_member,
            ).values_list('membership_id', 'sequence_order'))
            self.assertEqual(old_orders, before_orders[chore.pk])
        for assignment in ChoreAssignment.objects.filter(pk__in=before_assignments):
            self.assertEqual(
                (assignment.assigned_to_id, assignment.due_date, assignment.status),
                before_assignments[assignment.pk],
            )
        self.assertEqual(ChoreAssignment.objects.count(), 2)

    def test_member_enrollment_is_household_scoped(self):
        other_admin = User.objects.create_user(username='other-admin', password='pass')
        other_household = Household.objects.create(name='Other Home', admin=other_admin)
        other_membership = HouseholdMembership.objects.create(
            user=other_admin, household=other_household, is_admin=True,
        )
        other_chore = Chore.objects.create(household=other_household, title='Other chore')
        other_rotation = ChoreRotationMember.objects.create(
            chore=other_chore,
            membership=other_membership,
            sequence_order=0,
        )
        joined_membership = HouseholdMembership.objects.create(
            user=self.new_member,
            household=self.household,
        )

        enroll_member_in_active_chore_rotations(joined_membership)

        self.assertFalse(ChoreRotationMember.objects.filter(
            chore=other_chore,
            membership=joined_membership,
        ).exists())
        other_rotation.refresh_from_db()
        self.assertEqual(other_rotation.sequence_order, 0)

    def test_empty_active_rotation_starts_new_member_at_zero_and_retry_is_safe(self):
        empty_chore = Chore.objects.create(household=self.household, title='Empty rotation')
        membership = HouseholdMembership.objects.create(
            user=self.new_member,
            household=self.household,
        )

        enroll_member_in_active_chore_rotations(membership)
        enroll_member_in_active_chore_rotations(membership)

        self.assertEqual(
            ChoreRotationMember.objects.get(chore=empty_chore, membership=membership).sequence_order,
            0,
        )
        self.assertEqual(
            ChoreRotationMember.objects.filter(chore=empty_chore, membership=membership).count(),
            1,
        )

    def test_join_with_no_active_chores_still_succeeds(self):
        self.chore_one.is_active = False
        self.chore_one.save(update_fields=['is_active'])
        self.chore_two.is_active = False
        self.chore_two.save(update_fields=['is_active'])
        self.client.force_login(self.new_member)

        response = self.client.post(reverse('household_join'), {
            'join_code': self.household.join_code,
        })

        self.assertRedirects(response, reverse('household_members'))
        self.assertTrue(HouseholdMembership.objects.filter(
            user=self.new_member,
            household=self.household,
        ).exists())
