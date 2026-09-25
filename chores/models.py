import secrets
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from django.db import models


def generate_unique_join_code(length=8):
    """Generate a unique, uppercase alphanumeric join code without ambiguous characters."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        if not Household.objects.filter(join_code=code).exists():
            return code


class Household(models.Model):
    """Represents a shared living space with an administrator and join code."""
    name = models.CharField(
        max_length=100,
        help_text="The friendly name of your household (e.g. Apartment 4B, Maple House)."
    )
    join_code = models.CharField(
        max_length=12,
        unique=True,
        db_index=True,
        editable=False,
        help_text="Unique invite code used by housemates to join."
    )
    admin = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='administered_households',
        help_text="The designated administrator for the household."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.join_code:
            self.join_code = generate_unique_join_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def is_user_admin(self, user):
        """Check if the given user is the administrator of this household."""
        if not user or not user.is_authenticated:
            return False
        return self.admin_id == user.id

    def has_member(self, user):
        """Check if the given user is an enrolled member of this household."""
        if not user or not user.is_authenticated:
            return False
        return self.memberships.filter(user=user).exists()


class HouseholdMembership(models.Model):
    """Associates a User with a Household and denotes administrative standing."""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='household_memberships'
    )
    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    is_admin = models.BooleanField(
        default=False,
        help_text="Designates whether the member has administrative rights."
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'household'],
                name='unique_user_household'
            )
        ]
        ordering = ['-is_admin', 'joined_at']

    def __str__(self):
        role = "Admin" if self.is_admin else "Member"
        return f"{self.user.username} - {self.household.name} ({role})"


class Chore(models.Model):
    """A household chore definition and its recurrence configuration."""

    class FrequencyType(models.TextChoices):
        DAILY = 'DAILY', 'Daily'
        INTERVAL_DAYS = 'INTERVAL_DAYS', 'Every X days'
        WEEKLY = 'WEEKLY', 'Weekly'
        MONTHLY = 'MONTHLY', 'Monthly'

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name='chores',
    )
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    frequency_type = models.CharField(
        max_length=20,
        choices=FrequencyType.choices,
        default=FrequencyType.DAILY,
    )
    frequency_interval = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text='Number of days or weeks between occurrences; monthly uses months.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['title', 'id']

    def clean(self):
        super().clean()
        if self.frequency_type and self.frequency_type not in self.FrequencyType.values:
            raise ValidationError({'frequency_type': 'Select a valid recurrence frequency.'})
        if self.frequency_interval is not None and self.frequency_interval < 1:
            raise ValidationError({'frequency_interval': 'The interval must be at least 1.'})

    def __str__(self):
        return self.title


class ChoreRotationMember(models.Model):
    """An ordered household member slot in a chore's future rotation."""

    chore = models.ForeignKey(
        Chore,
        on_delete=models.CASCADE,
        related_name='rotation_members',
    )
    membership = models.ForeignKey(
        HouseholdMembership,
        on_delete=models.CASCADE,
        related_name='chore_rotations',
    )
    sequence_order = models.PositiveIntegerField()

    class Meta:
        ordering = ['sequence_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['chore', 'membership'],
                name='unique_chore_rotation_member',
            ),
            models.UniqueConstraint(
                fields=['chore', 'sequence_order'],
                name='unique_chore_rotation_order',
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.chore_id
            and self.membership_id
            and self.chore.household_id != self.membership.household_id
        ):
            raise ValidationError({
                'membership': 'Rotation members must belong to the chore household.'
            })

    def __str__(self):
        return f'{self.chore}: {self.membership.user} ({self.sequence_order})'
