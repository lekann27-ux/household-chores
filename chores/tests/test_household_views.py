from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from chores.models import Household, HouseholdMembership


class HouseholdViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='SecurePass123!')
        self.member = User.objects.create_user(username='member', password='SecurePass123!')
        self.other = User.objects.create_user(username='other', password='SecurePass123!')
        self.household = Household.objects.create(name='Elm Street', admin=self.admin)
        self.admin_membership = HouseholdMembership.objects.create(
            user=self.admin, household=self.household, is_admin=True,
        )
        self.member_membership = HouseholdMembership.objects.create(
            user=self.member, household=self.household,
        )

    def test_household_creation_creates_admin_household_and_membership(self):
        self.client.force_login(self.other)

        response = self.client.post(reverse('household_create'), {'name': 'New Home'})

        self.assertRedirects(response, reverse('household_members'))
        household = Household.objects.get(name='New Home')
        self.assertEqual(household.admin, self.other)
        self.assertTrue(HouseholdMembership.objects.filter(
            user=self.other, household=household, is_admin=True,
        ).exists())

    def test_existing_member_cannot_create_another_household(self):
        self.client.force_login(self.member)

        response = self.client.post(reverse('household_create'), {'name': 'Second Home'})

        self.assertRedirects(response, reverse('household_members'))
        self.assertFalse(Household.objects.filter(name='Second Home').exists())

    def test_join_code_is_case_insensitive_and_creates_membership(self):
        self.client.force_login(self.other)

        response = self.client.post(reverse('household_join'), {
            'join_code': self.household.join_code.lower(),
        })

        self.assertRedirects(response, reverse('household_members'))
        self.assertTrue(HouseholdMembership.objects.filter(
            user=self.other, household=self.household, is_admin=False,
        ).exists())

    def test_invalid_join_code_shows_validation_error(self):
        self.client.force_login(self.other)

        response = self.client.post(reverse('household_join'), {'join_code': 'NOT-A-CODE'})

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'], 'join_code',
            'Invalid join code. Please check with your household administrator.',
        )
        self.assertFalse(HouseholdMembership.objects.filter(user=self.other).exists())

    def test_member_without_household_is_redirected_to_create(self):
        self.client.force_login(self.other)

        response = self.client.get(reverse('household_members'))

        self.assertRedirects(response, reverse('household_create'))

    def test_only_household_members_can_view_roster(self):
        other_admin = User.objects.create_user(username='other_admin', password='SecurePass123!')
        other_household = Household.objects.create(name='Other Home', admin=other_admin)
        HouseholdMembership.objects.create(user=other_admin, household=other_household, is_admin=True)
        self.client.force_login(self.member)

        response = self.client.get(reverse('household_members'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Elm Street')
        self.assertNotContains(response, 'Other Home')
        self.assertContains(response, 'member')
        self.assertNotContains(response, 'id="btn-remove-member"')

    def test_non_admin_cannot_remove_member(self):
        self.client.force_login(self.member)

        response = self.client.post(reverse(
            'household_remove_member', args=[self.admin_membership.pk],
        ))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(HouseholdMembership.objects.filter(pk=self.admin_membership.pk).exists())

    def test_admin_can_remove_member_after_confirmation(self):
        self.client.force_login(self.admin)
        url = reverse('household_remove_member', args=[self.member_membership.pk])

        confirmation = self.client.get(url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(HouseholdMembership.objects.filter(pk=self.member_membership.pk).exists())

        response = self.client.post(url)

        self.assertRedirects(response, reverse('household_members'))
        self.assertFalse(HouseholdMembership.objects.filter(pk=self.member_membership.pk).exists())

    def test_admin_cannot_remove_self_and_cannot_target_other_household(self):
        self.client.force_login(self.admin)
        own_url = reverse('household_remove_member', args=[self.admin_membership.pk])
        self.assertRedirects(self.client.post(own_url), reverse('household_members'))
        self.assertTrue(HouseholdMembership.objects.filter(pk=self.admin_membership.pk).exists())

        other_admin = User.objects.create_user(username='other_admin', password='SecurePass123!')
        other_household = Household.objects.create(name='Other Home', admin=other_admin)
        other_membership = HouseholdMembership.objects.create(
            user=other_admin, household=other_household, is_admin=True,
        )
        response = self.client.post(reverse(
            'household_remove_member', args=[other_membership.pk],
        ))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(HouseholdMembership.objects.filter(pk=other_membership.pk).exists())

    def test_guests_are_redirected_to_login_for_household_views(self):
        for url in (reverse('household_create'), reverse('household_join'), reverse('household_members')):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, f'{reverse("login")}?next={url}')
