from django.contrib import admin
from .models import (
    Chore,
    ChoreAssignment,
    ChoreRotationMember,
    Household,
    HouseholdMembership,
    Notification,
)


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ('name', 'join_code', 'admin', 'created_at')
    search_fields = ('name', 'join_code', 'admin__username', 'admin__email')
    readonly_fields = ('join_code', 'created_at')


@admin.register(HouseholdMembership)
class HouseholdMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'household', 'is_admin', 'joined_at')
    list_filter = ('is_admin', 'household')
    search_fields = ('user__username', 'user__email', 'household__name')


@admin.register(Chore)
class ChoreAdmin(admin.ModelAdmin):
    list_display = ('title', 'household', 'frequency_type', 'frequency_interval', 'is_active', 'created_at')
    list_filter = ('frequency_type', 'is_active', 'household')
    search_fields = ('title', 'description', 'household__name')
    readonly_fields = ('created_at',)


@admin.register(ChoreRotationMember)
class ChoreRotationMemberAdmin(admin.ModelAdmin):
    list_display = ('chore', 'membership', 'sequence_order')
    list_filter = ('chore__household',)
    search_fields = ('chore__title', 'membership__user__username')


@admin.register(ChoreAssignment)
class ChoreAssignmentAdmin(admin.ModelAdmin):
    list_display = ('chore', 'assigned_to', 'due_date', 'status')
    list_filter = ('status', 'due_date', 'chore__household')
    search_fields = ('chore__title', 'assigned_to__user__username')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'household', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'household')
    search_fields = ('recipient__username', 'household__name', 'message')
    readonly_fields = ('created_at',)
