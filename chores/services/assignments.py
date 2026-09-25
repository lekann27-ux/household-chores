"""Assignment completion and overdue-state operations."""

from datetime import date, datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from chores.models import Chore, ChoreAssignment, ChoreRotationMember, HouseholdMembership
from chores.services.recurrence import calculate_next_due_date


@transaction.atomic
def complete_assignment(assignment_id, completed_by_membership):
    """Complete an assignment and create the next occurrence exactly once.

    An assignment may be completed by its assignee or household admin. The
    next due date is based on the completion date so late work does not cause
    an immediately overdue or back-to-back schedule.
    """
    if completed_by_membership.pk is None:
        raise PermissionDenied('A current household membership is required.')

    assignment = ChoreAssignment.objects.select_for_update().select_related(
        'chore__household', 'assigned_to',
    ).get(pk=assignment_id)
    chore = Chore.objects.select_for_update().get(pk=assignment.chore_id)
    household = chore.household
    completed_by_membership = HouseholdMembership.objects.select_related(
        'user',
    ).get(pk=completed_by_membership.pk)

    if completed_by_membership.household_id != household.pk:
        raise PermissionDenied('The member does not belong to this chore household.')
    is_assignee = assignment.assigned_to_id == completed_by_membership.pk
    is_admin = household.admin_id == completed_by_membership.user_id
    if not (is_assignee or is_admin):
        raise PermissionDenied('Only the assignee or household administrator can complete this chore.')

    if assignment.status == ChoreAssignment.Status.COMPLETED:
        return assignment
    if assignment.status not in (ChoreAssignment.Status.PENDING, ChoreAssignment.Status.OVERDUE):
        raise ValidationError('This assignment cannot be completed from its current state.')

    rotation = list(
        ChoreRotationMember.objects.select_for_update()
        .filter(chore=chore)
        .select_related('membership')
        .order_by('sequence_order', 'pk')
    )
    current_index = next(
        (index for index, item in enumerate(rotation)
         if item.membership_id == assignment.assigned_to_id),
        None,
    )
    if current_index is None or not rotation:
        raise ValidationError('The current assignee is not in this chore rotation.')

    completed_at = timezone.now()
    completion_date = timezone.localdate()
    assignment.status = ChoreAssignment.Status.COMPLETED
    assignment.completed_at = completed_at
    assignment.completed_by = completed_by_membership
    assignment.save(update_fields=['status', 'completed_at', 'completed_by'])

    if chore.is_active:
        next_member = rotation[(current_index + 1) % len(rotation)].membership
        next_due_date = calculate_next_due_date(
            chore.frequency_type,
            chore.frequency_interval,
            completion_date,
        )
        ChoreAssignment.objects.create(
            chore=chore,
            assigned_to=next_member,
            due_date=next_due_date,
            status=ChoreAssignment.Status.PENDING,
        )

    return assignment


@transaction.atomic
def mark_overdue_assignments(reference_date=None):
    """Mark pending assignments overdue after their calendar due date ends."""
    if reference_date is None:
        reference_date = timezone.localdate()
    if isinstance(reference_date, datetime) or not isinstance(reference_date, date):
        raise TypeError('reference_date must be a datetime.date, not a datetime.')

    return ChoreAssignment.objects.filter(
        status=ChoreAssignment.Status.PENDING,
        due_date__lt=reference_date,
    ).update(status=ChoreAssignment.Status.OVERDUE)
