"""Services for initial chore rotations and household member onboarding."""

from datetime import date, datetime

from django.db import transaction
from django.db.models import Max

from chores.models import Chore, ChoreAssignment, ChoreRotationMember, HouseholdMembership


@transaction.atomic
def initialize_chore_rotation(chore, initial_due_date):
    """Seed a new chore with its household members and first pending assignment.

    Existing initialization is returned unchanged, making retries safe. New
    rotation order follows membership join time and then primary key, so the
    household admin participates in the same deterministic queue as everyone
    else.
    """
    if chore.pk is None:
        raise ValueError('Save the chore before initializing its rotation.')
    if isinstance(initial_due_date, datetime) or not isinstance(initial_due_date, date):
        raise TypeError('initial_due_date must be a datetime.date, not a datetime.')

    locked_chore = Chore.objects.select_for_update().select_related('household').get(pk=chore.pk)
    existing_assignment = locked_chore.assignments.order_by('pk').first()
    if existing_assignment:
        return existing_assignment

    admin_membership, _ = HouseholdMembership.objects.get_or_create(
        household=locked_chore.household,
        user=locked_chore.household.admin,
        defaults={'is_admin': True},
    )
    if not admin_membership.is_admin:
        admin_membership.is_admin = True
        admin_membership.save(update_fields=['is_admin'])

    memberships = HouseholdMembership.objects.filter(
        household=locked_chore.household,
    ).order_by('joined_at', 'pk')
    for sequence_order, membership in enumerate(memberships):
        ChoreRotationMember.objects.get_or_create(
            chore=locked_chore,
            membership=membership,
            defaults={'sequence_order': sequence_order},
        )

    first_rotation_member = locked_chore.rotation_members.select_related(
        'membership',
    ).order_by('sequence_order', 'pk').first()
    if first_rotation_member is None:
        raise ValueError('A chore rotation requires at least one household member.')

    return ChoreAssignment.objects.create(
        chore=locked_chore,
        assigned_to=first_rotation_member.membership,
        due_date=initial_due_date,
        status=ChoreAssignment.Status.PENDING,
    )


@transaction.atomic
def enroll_member_in_active_chore_rotations(membership):
    """Append a newly joined household member to its active chore rotations.

    Existing sequence values and assignments are left untouched. If enrollment
    is retried for the same membership, existing rotation rows are preserved.
    """
    if membership.pk is None:
        raise ValueError('Save the membership before enrolling it in rotations.')
    membership = HouseholdMembership.objects.select_related('household').get(pk=membership.pk)

    chores = Chore.objects.filter(
        household_id=membership.household_id,
        is_active=True,
    ).order_by('pk')
    for chore in chores:
        locked_chore = Chore.objects.select_for_update().get(pk=chore.pk)
        if ChoreRotationMember.objects.filter(
            chore=locked_chore,
            membership=membership,
        ).exists():
            continue

        last_order = locked_chore.rotation_members.aggregate(
            last_order=Max('sequence_order'),
        )['last_order']
        next_order = 0 if last_order is None else last_order + 1
        ChoreRotationMember.objects.create(
            chore=locked_chore,
            membership=membership,
            sequence_order=next_order,
        )
