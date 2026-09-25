"""Household member operations that must preserve chore assignment integrity."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from chores.models import (
    Chore,
    ChoreAssignment,
    ChoreRotationMember,
    HouseholdMembership,
)


@transaction.atomic
def remove_member_from_household(membership_to_remove, admin_user):
    """Reassign active work, remove a member from queues, and compact ordering."""
    target_id = getattr(membership_to_remove, 'pk', membership_to_remove)
    target = HouseholdMembership.objects.select_for_update().select_related(
        'household', 'user',
    ).get(pk=target_id)
    household = target.household

    if not getattr(admin_user, 'is_authenticated', False) or household.admin_id != admin_user.pk:
        raise PermissionDenied('Only the household administrator can remove a member.')
    if not HouseholdMembership.objects.filter(
        household=household,
        user=admin_user,
    ).exists():
        raise PermissionDenied('The administrator must be a household member.')
    if target.user_id == household.admin_id or target.is_admin:
        raise ValidationError('The household administrator cannot be removed.')

    active_assignments = list(
        ChoreAssignment.objects.select_for_update()
        .filter(
            chore__household=household,
            assigned_to=target,
            status__in=(ChoreAssignment.Status.PENDING, ChoreAssignment.Status.OVERDUE),
        )
        .select_related('chore')
        .order_by('chore_id', 'pk')
    )

    reassigned_count = 0
    for assignment in active_assignments:
        rotation = list(
            ChoreRotationMember.objects.select_for_update()
            .filter(chore=assignment.chore)
            .select_related('membership')
            .order_by('sequence_order', 'pk')
        )
        target_index = next(
            (index for index, item in enumerate(rotation)
             if item.membership_id == target.pk),
            None,
        )
        if target_index is None:
            eligible = [item for item in rotation if item.membership_id != target.pk]
        else:
            eligible = [
                rotation[(target_index + offset) % len(rotation)]
                for offset in range(1, len(rotation) + 1)
                if rotation[(target_index + offset) % len(rotation)].membership_id != target.pk
            ]
        if not eligible:
            raise ValidationError(
                f'No remaining rotation member can take over {assignment.chore.title}.'
            )
        assignment.assigned_to = eligible[0].membership
        assignment.save(update_fields=['assigned_to'])
        reassigned_count += 1

    household_chore_ids = Chore.objects.filter(household=household).values_list('pk', flat=True)
    ChoreRotationMember.objects.filter(
        chore_id__in=household_chore_ids,
        membership=target,
    ).delete()

    for chore in Chore.objects.filter(household=household).order_by('pk'):
        rotations = list(
            ChoreRotationMember.objects.select_for_update()
            .filter(chore=chore)
            .order_by('sequence_order', 'pk')
        )
        for new_order, rotation_member in enumerate(rotations):
            if rotation_member.sequence_order != new_order:
                rotation_member.sequence_order = new_order
                rotation_member.save(update_fields=['sequence_order'])

    target.delete()
    return reassigned_count
