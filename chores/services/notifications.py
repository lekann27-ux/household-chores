"""Idempotent creation helpers for in-app chore notifications."""

from django.utils import timezone

from chores.models import ChoreAssignment, Notification


def generate_due_reminders(reference_date=None):
    """Create one reminder for each active chore assignment due on this date."""
    if reference_date is None:
        reference_date = timezone.localdate()

    due_assignments = ChoreAssignment.objects.filter(
        due_date=reference_date,
        status=ChoreAssignment.Status.PENDING,
        chore__is_active=True,
    ).select_related('chore__household', 'assigned_to__user')

    created_count = 0
    for assignment in due_assignments:
        _, created = Notification.objects.get_or_create(
            recipient_id=assignment.assigned_to.user_id,
            household_id=assignment.chore.household_id,
            assignment=assignment,
            notification_type=Notification.NotificationType.REMINDER,
            defaults={'message': f'{assignment.chore.title} is due today.'},
        )
        created_count += int(created)
    return created_count


def generate_overdue_alerts(assignments):
    """Notify each household admin once for each newly overdue active assignment."""
    created_count = 0
    for assignment in assignments:
        if not assignment.chore.is_active:
            continue
        _, created = Notification.objects.get_or_create(
            recipient_id=assignment.chore.household.admin_id,
            household_id=assignment.chore.household_id,
            assignment=assignment,
            notification_type=Notification.NotificationType.OVERDUE,
            defaults={'message': f'{assignment.chore.title} is overdue.'},
        )
        created_count += int(created)
    return created_count
