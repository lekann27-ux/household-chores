import secrets
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
