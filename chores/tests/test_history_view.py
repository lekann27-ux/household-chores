from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from chores.models import Chore, ChoreAssignment, Household, HouseholdMembership


class CompletedChoreHistoryViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='history-admin', password='pass')
        self.member = User.objects.create_user(username='history-member', password='pass')
        self.other_member = User.objects.create_user(username='history-other', password='pass')
        self.household = Household.objects.create(name='History Home', admin=self.admin)
        self.admin_membership = HouseholdMembership.objects.create(
            user=self.admin, household=self.household, is_admin=True,
        )
        self.member_membership = HouseholdMembership.objects.create(
            user=self.member, household=self.household,
        )
        self.other_membership = HouseholdMembership.objects.create(
            user=self.other_member, household=self.household,
        )
        self.dishes = Chore.objects.create(household=self.household, title='Wash dishes')
        self.bins = Chore.objects.create(household=self.household, title='Take bins out')
        self.today = timezone.localdate()
        self.client.force_login(self.member)

    def make_completed(self, chore, *, completed_by=None, days_ago=0, due_days_ago=1):
        completed_at = timezone.now() - timedelta(days=days_ago)
        return ChoreAssignment.objects.create(
            chore=chore,
            assigned_to=completed_by or self.member_membership,
            due_date=self.today - timedelta(days=due_days_ago),
            status=ChoreAssignment.Status.COMPLETED,
            completed_at=completed_at,
            completed_by=completed_by or self.member_membership,
        )

    def test_guest_is_redirected_to_login(self):
        self.client.logout()

        response = self.client.get(reverse('chore_history'))

        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("chore_history")}',
        )

    def test_history_displays_completion_details_and_only_completed_assignments(self):
        completed = self.make_completed(self.dishes)
        ChoreAssignment.objects.create(
            chore=self.bins,
            assigned_to=self.member_membership,
            due_date=self.today,
            status=ChoreAssignment.Status.PENDING,
        )

        response = self.client.get(reverse('chore_history'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chores/history.html')
        self.assertContains(response, 'Wash dishes')
        self.assertContains(response, 'History Home')
        self.assertContains(response, 'history-member')
        self.assertContains(response, completed.completed_at.strftime('%Y'))
        self.assertContains(response, completed.due_date.strftime('%b'))
        self.assertEqual(
            response.context['history_page'].object_list[0].due_date,
            completed.due_date,
        )
        self.assertEqual(list(response.context['history_page'].object_list), [completed])

    def test_filter_by_chore(self):
        dishes_assignment = self.make_completed(self.dishes)
        self.make_completed(self.bins)

        response = self.client.get(reverse('chore_history'), {'chore': self.dishes.pk})

        self.assertEqual(list(response.context['history_page'].object_list), [dishes_assignment])
        self.assertContains(response, 'Wash dishes')

    def test_filter_by_completing_member(self):
        member_assignment = self.make_completed(self.dishes)
        self.make_completed(self.bins, completed_by=self.other_membership)

        response = self.client.get(
            reverse('chore_history'), {'member': self.member_membership.pk},
        )

        self.assertEqual(list(response.context['history_page'].object_list), [member_assignment])

    def test_filter_by_completion_date_range_inclusive(self):
        inside = self.make_completed(self.dishes, days_ago=2)
        self.make_completed(self.bins, days_ago=5)
        start = (timezone.localdate() - timedelta(days=3)).isoformat()
        end = timezone.localdate().isoformat()

        response = self.client.get(
            reverse('chore_history'), {'date_from': start, 'date_to': end},
        )

        self.assertEqual(list(response.context['history_page'].object_list), [inside])

    def test_history_is_scoped_to_user_households_even_for_foreign_filter_id(self):
        local = self.make_completed(self.dishes)
        outside_admin = User.objects.create_user(username='secret-admin', password='pass')
        outside_home = Household.objects.create(name='Secret Home', admin=outside_admin)
        outside_membership = HouseholdMembership.objects.create(
            user=outside_admin, household=outside_home, is_admin=True,
        )
        outside_chore = Chore.objects.create(household=outside_home, title='Secret floors')
        ChoreAssignment.objects.create(
            chore=outside_chore,
            assigned_to=outside_membership,
            due_date=self.today,
            status=ChoreAssignment.Status.COMPLETED,
            completed_at=timezone.now(),
            completed_by=outside_membership,
        )

        response = self.client.get(reverse('chore_history'), {'chore': outside_chore.pk})

        self.assertEqual(list(response.context['history_page'].object_list), [local])
        self.assertContains(response, 'Wash dishes')
        self.assertNotContains(response, 'Secret Home')
        self.assertNotContains(response, 'Secret floors')
        self.assertFalse(response.context['form'].fields['chore'].queryset.filter(
            pk=outside_chore.pk,
        ).exists())

    def test_empty_history_and_user_without_household_have_clear_empty_states(self):
        response = self.client.get(reverse('chore_history'))
        self.assertContains(response, 'id="empty-history"')

        no_home = User.objects.create_user(username='history-no-home', password='pass')
        self.client.force_login(no_home)
        response = self.client.get(reverse('chore_history'))
        self.assertContains(response, 'id="empty-history"')
        self.assertEqual(response.context['history_page'].paginator.count, 0)

    def test_history_is_paginated_and_keeps_filters_in_page_links(self):
        for _ in range(26):
            self.make_completed(self.dishes)

        response = self.client.get(reverse('chore_history'), {'chore': self.dishes.pk})

        page = response.context['history_page']
        self.assertEqual(page.paginator.count, 26)
        self.assertEqual(len(page.object_list), 25)
        self.assertContains(response, f'?chore={self.dishes.pk}&amp;page=2')

        second_page = self.client.get(
            reverse('chore_history'), {'chore': self.dishes.pk, 'page': 2},
        )
        self.assertEqual(len(second_page.context['history_page'].object_list), 1)

    def test_reversed_date_range_is_rejected(self):
        self.make_completed(self.dishes)

        response = self.client.get(reverse('chore_history'), {
            'date_from': (self.today + timedelta(days=1)).isoformat(),
            'date_to': self.today.isoformat(),
        })

        self.assertTrue(response.context['form'].errors)
        self.assertContains(response, 'end date must be on or after the start date')
