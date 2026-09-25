from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from chores.models import Chore, ChoreAssignment, Household, HouseholdMembership
from chores.services.rotation import initialize_chore_rotation


class ChoreDashboardViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='dashboard-admin', password='pass')
        self.member = User.objects.create_user(username='dashboard-member', password='pass')
        self.other_member = User.objects.create_user(username='dashboard-other', password='pass')
        self.household = Household.objects.create(name='Dashboard Home', admin=self.admin)
        self.admin_membership = HouseholdMembership.objects.create(
            user=self.admin, household=self.household, is_admin=True,
        )
        self.member_membership = HouseholdMembership.objects.create(
            user=self.member, household=self.household,
        )
        self.other_membership = HouseholdMembership.objects.create(
            user=self.other_member, household=self.household,
        )
        self.today = timezone.localdate()

    def make_assignment(self, title, *, due_date, status, assigned_to=None, completed_by=None):
        chore = Chore.objects.create(household=self.household, title=title)
        assignment = initialize_chore_rotation(chore, due_date)
        assignment.assigned_to = assigned_to or self.member_membership
        assignment.status = status
        if status == ChoreAssignment.Status.COMPLETED:
            assignment.completed_at = timezone.now()
            assignment.completed_by = completed_by or self.member_membership
        assignment.save(update_fields=['assigned_to', 'status', 'completed_at', 'completed_by'])
        return chore, assignment

    def test_authenticated_user_can_access_dashboard(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chores/dashboard.html')
        self.assertContains(response, 'Chore Dashboard')

    def test_guest_is_redirected_to_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("dashboard")}',
        )

    def test_dashboard_limits_all_sections_to_user_households(self):
        self.make_assignment(
            'Local kitchen', due_date=self.today,
            status=ChoreAssignment.Status.PENDING,
        )
        outside_admin = User.objects.create_user(username='outside-admin', password='pass')
        outside_household = Household.objects.create(name='Private Other Home', admin=outside_admin)
        HouseholdMembership.objects.create(
            user=outside_admin, household=outside_household, is_admin=True,
        )
        outside_chore = Chore.objects.create(household=outside_household, title='Private task')
        initialize_chore_rotation(outside_chore, self.today)
        self.client.force_login(self.member)

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'Dashboard Home')
        self.assertContains(response, 'Local kitchen')
        self.assertNotContains(response, 'Private Other Home')
        self.assertNotContains(response, 'Private task')

    def test_dashboard_shows_my_overdue_due_today_upcoming_and_recently_completed(self):
        overdue_chore, overdue = self.make_assignment(
            'Overdue sink', due_date=self.today - timedelta(days=2),
            status=ChoreAssignment.Status.OVERDUE,
        )
        due_chore, _ = self.make_assignment(
            'Today dishes', due_date=self.today,
            status=ChoreAssignment.Status.PENDING,
        )
        future_chore, _ = self.make_assignment(
            'Future bins', due_date=self.today + timedelta(days=3),
            status=ChoreAssignment.Status.PENDING,
        )
        completed_chore, _ = self.make_assignment(
            'Finished bath', due_date=self.today - timedelta(days=1),
            status=ChoreAssignment.Status.COMPLETED,
        )
        self.client.force_login(self.member)

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, overdue_chore.title)
        self.assertContains(response, due_chore.title)
        self.assertContains(response, future_chore.title)
        self.assertContains(response, completed_chore.title)
        self.assertContains(response, 'Overdue')
        self.assertContains(response, 'Pending')
        self.assertContains(response, 'Completed')
        self.assertEqual(response.context['my_overdue'][0].pk, overdue.pk)
        self.assertEqual(len(response.context['my_due_today']), 1)
        self.assertEqual(len(response.context['my_upcoming']), 1)
        self.assertEqual(len(response.context['recent_completed']), 1)

    def test_due_pending_item_is_displayed_as_overdue_before_scanner_runs(self):
        chore, assignment = self.make_assignment(
            'Scanner pending', due_date=self.today - timedelta(days=1),
            status=ChoreAssignment.Status.PENDING,
        )
        self.client.force_login(self.member)

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, chore.title)
        self.assertEqual(response.context['my_overdue'][0].display_status, ChoreAssignment.Status.OVERDUE)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, ChoreAssignment.Status.PENDING)

    def test_upcoming_rotation_preview_shows_next_member_and_due_date(self):
        chore, _ = self.make_assignment(
            'Rotation preview', due_date=self.today + timedelta(days=4),
            status=ChoreAssignment.Status.PENDING,
        )
        self.client.force_login(self.member)

        response = self.client.get(reverse('dashboard'))

        rotation = next(
            item for item in response.context['upcoming_rotations']
            if item.pk == chore.pk
        )
        self.assertEqual(rotation.current_assignment.due_date, self.today + timedelta(days=4))
        self.assertEqual(rotation.next_member, self.other_membership)
        self.assertContains(response, 'Upcoming Rotations')

    def test_quick_completion_posts_through_existing_assignment_service(self):
        chore, assignment = self.make_assignment(
            'Quick clean', due_date=self.today,
            status=ChoreAssignment.Status.PENDING,
        )
        self.client.force_login(self.member)
        self.assertContains(
            self.client.get(reverse('dashboard')),
            reverse('complete_assignment', args=[assignment.pk]),
        )

        response = self.client.post(reverse('complete_assignment', args=[assignment.pk]))

        self.assertRedirects(response, reverse('chore_list'))
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, ChoreAssignment.Status.COMPLETED)
        self.assertEqual(assignment.completed_by, self.member_membership)
        self.assertTrue(ChoreAssignment.objects.filter(
            chore=chore,
            status=ChoreAssignment.Status.PENDING,
        ).exists())

    def test_household_admin_can_quick_complete_another_members_assignment(self):
        _, assignment = self.make_assignment(
            'Admin quick action', due_date=self.today,
            status=ChoreAssignment.Status.PENDING,
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse('complete_assignment', args=[assignment.pk]))

        self.assertRedirects(response, reverse('chore_list'))
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, ChoreAssignment.Status.COMPLETED)
        self.assertEqual(assignment.completed_by, self.admin_membership)

    def test_dashboard_has_empty_states_for_user_without_a_household(self):
        no_house_user = User.objects.create_user(username='no-house', password='pass')
        self.client.force_login(no_house_user)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dashboard-no-household')
        self.assertContains(response, 'empty-my-chores')
        self.assertContains(response, 'empty-household-chores')
        self.assertContains(response, 'empty-upcoming-rotations')
        self.assertContains(response, 'empty-recent-completed')
