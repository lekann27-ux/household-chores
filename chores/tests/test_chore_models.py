from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from chores.models import (
    Chore,
    ChoreAssignment,
    ChoreRotationMember,
    Household,
    HouseholdMembership,
)


class ChoreModelTests(TestCase):
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

    def test_chore_defaults_and_frequency_choices(self):
        chore = Chore.objects.create(household=self.household, title='Sweep')

        self.assertEqual(chore.frequency_type, Chore.FrequencyType.DAILY)
        self.assertEqual(chore.frequency_interval, 1)
        self.assertTrue(chore.is_active)
        self.assertEqual(chore.description, '')
        self.assertEqual(chore.get_frequency_type_display(), 'Daily')

    def test_chore_rejects_nonpositive_interval(self):
        chore = Chore(
            household=self.household,
            title='Sweep',
            frequency_interval=0,
        )

        with self.assertRaises(ValidationError):
            chore.full_clean()

    def test_rotation_members_are_ordered_and_unique(self):
        chore = Chore.objects.create(household=self.household, title='Sweep')
        second = ChoreRotationMember.objects.create(
            chore=chore, membership=self.member_membership, sequence_order=1,
        )
        first = ChoreRotationMember.objects.create(
            chore=chore, membership=self.admin_membership, sequence_order=0,
        )

        self.assertEqual(list(chore.rotation_members.all()), [first, second])

        with self.assertRaises(IntegrityError), transaction.atomic():
            ChoreRotationMember.objects.create(
                chore=chore, membership=self.admin_membership, sequence_order=2,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChoreRotationMember.objects.create(
                chore=chore, membership=self.member_membership, sequence_order=0,
            )

    def test_rotation_member_must_belong_to_chore_household(self):
        other_admin = User.objects.create_user(username='other-admin', password='pass')
        other_household = Household.objects.create(name='Other Home', admin=other_admin)
        other_membership = HouseholdMembership.objects.create(
            user=other_admin, household=other_household, is_admin=True,
        )
        chore = Chore.objects.create(household=self.household, title='Sweep')
        rotation_member = ChoreRotationMember(
            chore=chore, membership=other_membership, sequence_order=0,
        )

        with self.assertRaises(ValidationError):
            rotation_member.full_clean()

    def test_deleting_chore_cascades_to_rotation_members(self):
        chore = Chore.objects.create(household=self.household, title='Sweep')
        ChoreRotationMember.objects.create(
            chore=chore, membership=self.admin_membership, sequence_order=0,
        )

        chore.delete()

        self.assertFalse(ChoreRotationMember.objects.exists())

    def test_assignment_rejects_member_from_another_household(self):
        other_admin = User.objects.create_user(username='other-admin', password='pass')
        other_household = Household.objects.create(name='Other Home', admin=other_admin)
        other_membership = HouseholdMembership.objects.create(
            user=other_admin, household=other_household, is_admin=True,
        )
        chore = Chore.objects.create(household=self.household, title='Sweep')
        assignment = ChoreAssignment(
            chore=chore,
            assigned_to=other_membership,
            due_date='2026-10-03',
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()
