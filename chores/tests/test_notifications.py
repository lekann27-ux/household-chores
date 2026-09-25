from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
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
from chores.services.assignments import mark_overdue_assignments
from chores.services.notifications import generate_due_reminders
from chores.services.rotation import initialize_chore_rotation


class ChoreNotificationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='notify-admin', password='pass')
        self.member = User.objects.create_user(username='notify-member', password='pass')
        self.household = Household.objects.create(name='Notification Home', admin=self.admin)
        self.admin_membership = HouseholdMembership.objects.create(
            user=self.admin, household=self.household, is_admin=True,
        )
        self.member_membership = HouseholdMembership.objects.create(
            user=self.member, household=self.household,
        )
        self.chore = Chore.objects.create(
            household=self.household, title='Wash dishes',
        )
        self.today = date(2026, 6, 10)
        self.assignment = initialize_chore_rotation(self.chore, self.today)
        self.assignment.assigned_to = self.member_membership
        self.assignment.save(update_fields=['assigned_to'])

    def make_other_household(self):
        admin = User.objects.create_user(username='other-notify-admin', password='pass')
        household = Household.objects.create(name='Other Notification Home', admin=admin)
        membership = HouseholdMembership.objects.create(
            user=admin, household=household, is_admin=True,
        )
        chore = Chore.objects.create(household=household, title='Private chore')
        assignment = ChoreAssignment.objects.create(
            chore=chore,
            assigned_to=membership,
            due_date=self.today,
            status=ChoreAssignment.Status.PENDING,
        )
        notification = Notification.objects.create(
            recipient=admin,
            household=household,
            assignment=assignment,
            notification_type=Notification.NotificationType.REMINDER,
            message='Private reminder',
        )
        return admin, notification

    def test_due_reminder_is_created_for_assignee_only(self):
        created = generate_due_reminders(self.today)

        self.assertEqual(created, 1)
        notification = Notification.objects.get()
        self.assertEqual(notification.recipient, self.member)
        self.assertEqual(notification.household, self.household)
        self.assertEqual(notification.assignment, self.assignment)
        self.assertEqual(notification.notification_type, Notification.NotificationType.REMINDER)
        self.assertFalse(notification.is_read)
        self.assertIsNotNone(notification.created_at)

    def test_due_reminder_generation_is_idempotent_per_assignment_event(self):
        self.assertEqual(generate_due_reminders(self.today), 1)
        self.assertEqual(generate_due_reminders(self.today), 0)
        self.assertEqual(Notification.objects.count(), 1)

    def test_due_reminder_command_generates_reminders_for_today(self):
        output = StringIO()
        with patch('chores.services.notifications.timezone.localdate', return_value=self.today):
            call_command('send_chore_reminders', stdout=output)

        self.assertIn('Created 1 due reminder(s).', output.getvalue())
        self.assertEqual(Notification.objects.get().recipient, self.member)

    def test_inactive_chores_and_completed_assignments_do_not_receive_reminders(self):
        self.chore.is_active = False
        self.chore.save(update_fields=['is_active'])
        self.assertEqual(generate_due_reminders(self.today), 0)

        self.chore.is_active = True
        self.chore.save(update_fields=['is_active'])
        self.assignment.status = ChoreAssignment.Status.COMPLETED
        self.assignment.completed_at = timezone.now()
        self.assignment.save(update_fields=['status', 'completed_at'])

        self.assertEqual(generate_due_reminders(self.today), 0)
        self.assertFalse(Notification.objects.exists())

    def test_overdue_scanner_notifies_admin_without_rotating_or_reassigning(self):
        original_assignee = self.assignment.assigned_to_id

        count = mark_overdue_assignments(self.today + timedelta(days=1))

        self.assertEqual(count, 1)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ChoreAssignment.Status.OVERDUE)
        self.assertEqual(self.assignment.assigned_to_id, original_assignee)
        self.assertEqual(ChoreAssignment.objects.filter(chore=self.chore).count(), 1)
        notification = Notification.objects.get()
        self.assertEqual(notification.recipient, self.admin)
        self.assertEqual(notification.notification_type, Notification.NotificationType.OVERDUE)

    def test_overdue_notification_is_not_duplicated_by_repeated_scans(self):
        self.assertEqual(mark_overdue_assignments(self.today + timedelta(days=1)), 1)
        self.assertEqual(mark_overdue_assignments(self.today + timedelta(days=1)), 0)
        self.assertEqual(Notification.objects.filter(
            notification_type=Notification.NotificationType.OVERDUE,
        ).count(), 1)

    def test_overdue_assignment_for_inactive_chore_is_not_notified(self):
        self.chore.is_active = False
        self.chore.save(update_fields=['is_active'])

        mark_overdue_assignments(self.today + timedelta(days=1))

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ChoreAssignment.Status.OVERDUE)
        self.assertFalse(Notification.objects.exists())

    def test_notification_list_is_authenticated_and_limited_to_recipient(self):
        notification = Notification.objects.create(
            recipient=self.member,
            household=self.household,
            assignment=self.assignment,
            notification_type=Notification.NotificationType.REMINDER,
            message='Wash dishes is due today.',
        )
        self.client.force_login(self.member)

        response = self.client.get(reverse('notification_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chores/notifications.html')
        self.assertEqual(list(response.context['notification_page'].object_list), [notification])
        self.assertContains(response, notification.message)

    def test_notification_list_and_read_endpoint_are_household_scoped(self):
        other_admin, foreign_notification = self.make_other_household()
        local = Notification.objects.create(
            recipient=self.member,
            household=self.household,
            assignment=self.assignment,
            notification_type=Notification.NotificationType.REMINDER,
            message='Local reminder',
        )
        self.client.force_login(self.member)

        response = self.client.get(reverse('notification_list'))

        self.assertEqual(list(response.context['notification_page'].object_list), [local])
        self.assertContains(response, 'Local reminder')
        self.assertNotContains(response, 'Private reminder')
        self.assertEqual(
            self.client.post(reverse('mark_notification_read', args=[foreign_notification.pk])).status_code,
            404,
        )
        foreign_notification.refresh_from_db()
        self.assertFalse(foreign_notification.is_read)

        self.client.force_login(other_admin)
        self.assertContains(self.client.get(reverse('notification_list')), 'Private reminder')

    def test_marking_notification_read_decrements_unread_badge_and_is_idempotent(self):
        notification = Notification.objects.create(
            recipient=self.member,
            household=self.household,
            assignment=self.assignment,
            notification_type=Notification.NotificationType.REMINDER,
            message='Wash dishes is due today.',
        )
        self.client.force_login(self.member)

        unread_response = self.client.get(reverse('notification_list'))
        self.assertEqual(unread_response.context['unread_notification_count'], 1)
        self.assertContains(unread_response, 'unread-notification-count')

        response = self.client.post(reverse('mark_notification_read', args=[notification.pk]))

        self.assertRedirects(response, reverse('notification_list'))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        read_response = self.client.get(reverse('notification_list'))
        self.assertEqual(read_response.context['unread_notification_count'], 0)
        self.assertNotContains(read_response, 'unread-notification-count')
        self.assertEqual(
            self.client.post(reverse('mark_notification_read', args=[notification.pk])).status_code,
            302,
        )

    def test_only_post_can_mark_notification_read_and_guests_are_redirected(self):
        notification = Notification.objects.create(
            recipient=self.member,
            household=self.household,
            assignment=self.assignment,
            notification_type=Notification.NotificationType.REMINDER,
            message='Wash dishes is due today.',
        )
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(reverse('mark_notification_read', args=[notification.pk])).status_code,
            405,
        )
        self.client.logout()
        response = self.client.get(reverse('notification_list'))
        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("notification_list")}',
        )

    def test_empty_notification_state_and_navigation_are_available(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse('notification_list'))

        self.assertContains(response, 'id="empty-notifications"')
        self.assertContains(response, 'id="nav-notifications"')
