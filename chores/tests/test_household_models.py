from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from chores.models import Household, HouseholdMembership


class HouseholdModelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')

    def test_household_generates_unique_uppercase_alphanumeric_join_code(self):
        first = Household.objects.create(name='First home', admin=self.admin)
        second = Household.objects.create(name='Second home', admin=self.admin)

        self.assertEqual(len(first.join_code), 8)
        self.assertRegex(first.join_code, r'^[A-Z2-9]{8}$')
        self.assertNotEqual(first.join_code, second.join_code)

    def test_membership_rejects_duplicate_user_household_pair(self):
        household = Household.objects.create(name='Home', admin=self.admin)
        HouseholdMembership.objects.create(user=self.admin, household=household, is_admin=True)

        with self.assertRaises(IntegrityError), transaction.atomic():
            HouseholdMembership.objects.create(user=self.admin, household=household)

    def test_household_and_memberships_cascade_when_admin_is_deleted(self):
        household = Household.objects.create(name='Home', admin=self.admin)
        member = User.objects.create_user(username='member', password='pass')
        HouseholdMembership.objects.create(user=self.admin, household=household, is_admin=True)
        HouseholdMembership.objects.create(user=member, household=household)

        self.admin.delete()

        self.assertFalse(Household.objects.filter(pk=household.pk).exists())
        self.assertFalse(HouseholdMembership.objects.filter(household_id=household.pk).exists())

    def test_admin_and_membership_helpers(self):
        household = Household.objects.create(name='Home', admin=self.admin)
        membership = HouseholdMembership.objects.create(user=self.admin, household=household, is_admin=True)

        self.assertTrue(household.is_user_admin(self.admin))
        self.assertTrue(household.has_member(self.admin))
        self.assertFalse(household.is_user_admin(None))
        self.assertEqual(str(membership), 'admin - Home (Admin)')
