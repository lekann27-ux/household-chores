from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from chores.models import Chore, ChoreRotationMember, Household, HouseholdMembership


class ChoreCrudViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='SecurePass123!')
        self.member = User.objects.create_user(username='member', password='SecurePass123!')
        self.other_admin = User.objects.create_user(username='other-admin', password='SecurePass123!')
        self.household = Household.objects.create(name='First Home', admin=self.admin)
        self.other_household = Household.objects.create(name='Second Home', admin=self.other_admin)
        self.admin_membership = HouseholdMembership.objects.create(
            user=self.admin, household=self.household, is_admin=True,
        )
        HouseholdMembership.objects.create(user=self.member, household=self.household)
        HouseholdMembership.objects.create(
            user=self.other_admin, household=self.other_household, is_admin=True,
        )
        self.chore = Chore.objects.create(household=self.household, title='Clean kitchen')
        self.other_chore = Chore.objects.create(household=self.other_household, title='Mow lawn')

    def chore_data(self, **overrides):
        data = {
            'title': 'Wash dishes',
            'description': 'After dinner',
            'frequency_type': Chore.FrequencyType.INTERVAL_DAYS,
            'frequency_interval': '3',
            'is_active': 'on',
        }
        data.update(overrides)
        return data

    def test_admin_list_shows_only_own_household_chores_and_admin_actions(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('chore_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Clean kitchen')
        self.assertNotContains(response, 'Mow lawn')
        self.assertContains(response, reverse('chore_create'))
        self.assertContains(response, reverse('chore_update', args=[self.chore.pk]))

    def test_member_can_view_chores_but_not_admin_actions(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse('chore_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Clean kitchen')
        self.assertNotContains(response, reverse('chore_create'))
        self.assertNotContains(response, reverse('chore_update', args=[self.chore.pk]))

    def test_admin_can_create_chore_and_household_is_assigned_server_side(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse('chore_create'), self.chore_data())

        self.assertRedirects(response, reverse('chore_list'))
        chore = Chore.objects.get(title='Wash dishes')
        self.assertEqual(chore.household, self.household)
        self.assertEqual(chore.frequency_type, Chore.FrequencyType.INTERVAL_DAYS)
        self.assertEqual(chore.frequency_interval, 3)
        self.assertEqual(chore.description, 'After dinner')

    def test_invalid_interval_is_rejected_without_creating_chore(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('chore_create'), self.chore_data(frequency_interval='0'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'frequency_interval', 'The interval must be at least 1.')
        self.assertFalse(Chore.objects.filter(title='Wash dishes').exists())

    def test_admin_can_update_schedule_details_and_active_status(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('chore_update', args=[self.chore.pk]),
            self.chore_data(title='Clean kitchen deeply', is_active=''),
        )

        self.assertRedirects(response, reverse('chore_list'))
        self.chore.refresh_from_db()
        self.assertEqual(self.chore.title, 'Clean kitchen deeply')
        self.assertFalse(self.chore.is_active)
        self.assertEqual(self.chore.frequency_interval, 3)

    def test_admin_confirms_then_deletes_chore_and_rotation_rows(self):
        rotation = ChoreRotationMember.objects.create(
            chore=self.chore, membership=self.admin_membership, sequence_order=0,
        )
        self.client.force_login(self.admin)
        url = reverse('chore_delete', args=[self.chore.pk])

        confirmation = self.client.get(url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(Chore.objects.filter(pk=self.chore.pk).exists())

        response = self.client.post(url)

        self.assertRedirects(response, reverse('chore_list'))
        self.assertFalse(Chore.objects.filter(pk=self.chore.pk).exists())
        self.assertFalse(ChoreRotationMember.objects.filter(pk=rotation.pk).exists())

    def test_non_admin_is_forbidden_from_create_edit_and_delete(self):
        self.client.force_login(self.member)

        urls_and_methods = (
            (reverse('chore_create'), 'post'),
            (reverse('chore_update', args=[self.chore.pk]), 'post'),
            (reverse('chore_delete', args=[self.chore.pk]), 'post'),
        )
        for url, method in urls_and_methods:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url, self.chore_data())
                self.assertEqual(response.status_code, 403)
        self.assertTrue(Chore.objects.filter(pk=self.chore.pk).exists())

    def test_other_household_chore_cannot_be_viewed_edited_or_deleted(self):
        self.client.force_login(self.admin)

        edit = self.client.get(reverse('chore_update', args=[self.other_chore.pk]))
        delete = self.client.get(reverse('chore_delete', args=[self.other_chore.pk]))
        self.assertEqual(edit.status_code, 404)
        self.assertEqual(delete.status_code, 404)

        edit_post = self.client.post(
            reverse('chore_update', args=[self.other_chore.pk]),
            self.chore_data(title='Hijacked'),
        )
        delete_post = self.client.post(reverse('chore_delete', args=[self.other_chore.pk]))
        self.assertEqual(edit_post.status_code, 404)
        self.assertEqual(delete_post.status_code, 404)
        self.assertTrue(Chore.objects.filter(pk=self.other_chore.pk).exists())
        self.assertFalse(Chore.objects.filter(title='Hijacked').exists())

    def test_user_without_household_is_redirected_and_guest_redirects_to_login(self):
        outsider = User.objects.create_user(username='outsider', password='SecurePass123!')
        self.client.force_login(outsider)
        response = self.client.get(reverse('chore_list'))
        self.assertRedirects(response, reverse('household_create'))

        self.client.logout()
        response = self.client.get(reverse('chore_list'))
        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("chore_list")}',
        )
