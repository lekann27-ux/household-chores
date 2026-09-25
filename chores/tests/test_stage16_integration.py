from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from chores.models import (
    Chore,
    ChoreAssignment,
    Household,
    HouseholdMembership,
    Notification,
)
from chores.services.assignments import complete_assignment, mark_overdue_assignments
from chores.services.members import remove_member_from_household
from chores.services.rotation import initialize_chore_rotation


class Stage16IntegrationTests(TestCase):
    def make_household(self, name, admin_name):
        admin = User.objects.create_user(username=admin_name, password='pass')
        household = Household.objects.create(name=name, admin=admin)
        membership = HouseholdMembership.objects.create(
            user=admin, household=household, is_admin=True,
        )
        return admin, household, membership

    def test_single_member_household_repeats_rotation_and_recurrence(self):
        admin, household, admin_membership = self.make_household('Solo Home', 'solo-admin')
        chore = Chore.objects.create(
            household=household,
            title='Daily kitchen',
            frequency_type=Chore.FrequencyType.DAILY,
            frequency_interval=1,
        )
        first = initialize_chore_rotation(chore, date(2026, 5, 1))
        self.assertEqual(chore.rotation_members.count(), 1)
        self.assertEqual(first.assigned_to, admin_membership)

        with patch('chores.services.assignments.timezone.localdate', return_value=date(2026, 5, 4)):
            complete_assignment(first.pk, admin_membership)
        second = ChoreAssignment.objects.get(chore=chore, status=ChoreAssignment.Status.PENDING)
        self.assertEqual(second.assigned_to, admin_membership)
        self.assertEqual(second.due_date, date(2026, 5, 5))

        with patch('chores.services.assignments.timezone.localdate', return_value=date(2026, 5, 5)):
            complete_assignment(second.pk, admin_membership)
        third = ChoreAssignment.objects.get(chore=chore, status=ChoreAssignment.Status.PENDING)
        self.assertEqual(third.assigned_to, admin_membership)
        self.assertEqual(third.due_date, date(2026, 5, 6))
        self.assertEqual(ChoreAssignment.objects.filter(chore=chore).count(), 3)
        self.assertEqual(admin.username, 'solo-admin')

    def test_late_overdue_assignment_stays_until_completion_then_advances_from_today(self):
        admin, household, admin_membership = self.make_household('Late Home', 'late-admin')
        member = User.objects.create_user(username='late-member', password='pass')
        member_membership = HouseholdMembership.objects.create(user=member, household=household)
        chore = Chore.objects.create(
            household=household,
            title='Weekly floors',
            frequency_type=Chore.FrequencyType.WEEKLY,
            frequency_interval=1,
        )
        assignment = initialize_chore_rotation(chore, date(2026, 1, 1))
        assignment.assigned_to = admin_membership
        assignment.save(update_fields=['assigned_to'])

        self.assertEqual(mark_overdue_assignments(date(2026, 1, 8)), 1)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, ChoreAssignment.Status.OVERDUE)
        self.assertEqual(assignment.assigned_to, admin_membership)
        self.assertFalse(ChoreAssignment.objects.filter(
            chore=chore, status=ChoreAssignment.Status.PENDING,
        ).exists())

        with patch('chores.services.assignments.timezone.localdate', return_value=date(2026, 2, 10)):
            complete_assignment(assignment.pk, admin_membership)

        next_assignment = ChoreAssignment.objects.get(
            chore=chore, status=ChoreAssignment.Status.PENDING,
        )
        self.assertEqual(next_assignment.assigned_to, member_membership)
        self.assertEqual(next_assignment.due_date, date(2026, 2, 17))
        self.assertGreater(next_assignment.due_date, date(2026, 2, 10))
        self.assertEqual(ChoreAssignment.objects.filter(chore=chore).count(), 2)
        self.assertEqual(admin.username, 'late-admin')

    def test_removing_all_members_leaves_admin_rotation_and_reassigns_active_work(self):
        admin, household, admin_membership = self.make_household('Removal Home', 'remove-admin')
        users = [
            User.objects.create_user(username=f'remove-{number}', password='pass')
            for number in range(2)
        ]
        memberships = [
            HouseholdMembership.objects.create(user=user, household=household)
            for user in users
        ]
        chore = Chore.objects.create(household=household, title='Shared kitchen')
        assignment = initialize_chore_rotation(chore, date(2026, 3, 1))
        assignment.assigned_to = memberships[0]
        assignment.save(update_fields=['assigned_to'])

        remove_member_from_household(memberships[0], admin)
        remove_member_from_household(memberships[1], admin)

        assignment.refresh_from_db()
        rotations = list(chore.rotation_members.order_by('sequence_order'))
        self.assertEqual(assignment.assigned_to, admin_membership)
        self.assertEqual([(item.membership_id, item.sequence_order) for item in rotations], [
            (admin_membership.pk, 0),
        ])
        self.assertEqual(HouseholdMembership.objects.filter(household=household).count(), 1)

    def test_removed_member_cannot_continue_accessing_household_or_assignments(self):
        admin, household, admin_membership = self.make_household('Protected Home', 'protect-admin')
        removed_user = User.objects.create_user(username='removed-user', password='pass')
        removed_membership = HouseholdMembership.objects.create(
            user=removed_user, household=household,
        )
        chore = Chore.objects.create(household=household, title='Private bathroom')
        assignment = initialize_chore_rotation(chore, date(2026, 4, 1))
        assignment.assigned_to = removed_membership
        assignment.save(update_fields=['assigned_to'])
        remove_member_from_household(removed_membership, admin)
        self.client.force_login(removed_user)

        self.assertRedirects(self.client.get(reverse('household_members')), reverse('household_create'))
        self.assertRedirects(self.client.get(reverse('chore_list')), reverse('household_create'))
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Protected Home')
        self.assertNotContains(self.client.get(reverse('chore_history')), 'Private bathroom')
        self.assertContains(self.client.get(reverse('notification_list')), 'id="empty-notifications"')
        self.assertEqual(
            self.client.post(reverse('complete_assignment', args=[assignment.pk])).status_code,
            403,
        )
        self.assertTrue(Household.objects.filter(pk=household.pk).exists())

    def test_repeated_completion_endpoint_posts_create_one_next_occurrence(self):
        admin, household, admin_membership = self.make_household('Retry Home', 'retry-admin')
        chore = Chore.objects.create(household=household, title='Retry chore')
        assignment = initialize_chore_rotation(chore, date(2026, 6, 1))
        self.client.force_login(admin)
        url = reverse('complete_assignment', args=[assignment.pk])

        with patch('chores.services.assignments.timezone.localdate', return_value=date(2026, 6, 2)):
            first_response = self.client.post(url)
            assignment.refresh_from_db()
            completed_at = assignment.completed_at
            second_response = self.client.post(url)

        self.assertRedirects(first_response, reverse('chore_list'))
        self.assertRedirects(second_response, reverse('chore_list'))
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, ChoreAssignment.Status.COMPLETED)
        self.assertEqual(assignment.completed_at, completed_at)
        self.assertEqual(assignment.completed_by, admin_membership)
        self.assertEqual(ChoreAssignment.objects.filter(chore=chore).count(), 2)
        self.assertEqual(ChoreAssignment.objects.filter(
            chore=chore, status=ChoreAssignment.Status.PENDING,
        ).count(), 1)

    def test_household_isolation_covers_chore_assignment_history_notifications_and_roster(self):
        admin, household, admin_membership = self.make_household('Local Home', 'local-admin')
        local_member = User.objects.create_user(username='local-member', password='pass')
        local_membership = HouseholdMembership.objects.create(user=local_member, household=household)
        local_chore = Chore.objects.create(household=household, title='Local chore')
        local_assignment = initialize_chore_rotation(local_chore, date(2026, 7, 1))
        local_assignment.assigned_to = local_membership
        local_assignment.save(update_fields=['assigned_to'])

        other_admin = User.objects.create_user(username='foreign-admin', password='pass')
        other_household = Household.objects.create(name='Foreign Home', admin=other_admin)
        other_admin_membership = HouseholdMembership.objects.create(
            user=other_admin, household=other_household, is_admin=True,
        )
        other_chore = Chore.objects.create(household=other_household, title='Foreign chore')
        other_assignment = initialize_chore_rotation(other_chore, date(2026, 7, 1))
        other_assignment.status = ChoreAssignment.Status.COMPLETED
        other_assignment.completed_at = timezone.now()
        other_assignment.completed_by = other_admin_membership
        other_assignment.save(update_fields=['status', 'completed_at', 'completed_by'])
        foreign_notification = Notification.objects.create(
            recipient=other_admin,
            household=other_household,
            assignment=other_assignment,
            notification_type=Notification.NotificationType.REMINDER,
            message='Foreign reminder',
        )
        self.client.force_login(admin)

        self.assertContains(self.client.get(reverse('chore_list')), 'Local chore')
        self.assertNotContains(self.client.get(reverse('chore_list')), 'Foreign chore')
        self.assertContains(self.client.get(reverse('household_members')), 'Local Home')
        self.assertNotContains(self.client.get(reverse('household_members')), 'Foreign Home')
        self.assertNotContains(self.client.get(reverse('chore_history')), 'Foreign chore')
        self.assertNotContains(self.client.get(reverse('notification_list')), 'Foreign reminder')
        self.assertEqual(
            self.client.post(reverse('complete_assignment', args=[other_assignment.pk])).status_code,
            404,
        )
        other_assignment.refresh_from_db()
        foreign_notification.refresh_from_db()
        self.assertEqual(other_assignment.status, ChoreAssignment.Status.COMPLETED)
        self.assertFalse(foreign_notification.is_read)
        self.assertEqual(admin.username, 'local-admin')
