from django.contrib import admin
from .models import Household, HouseholdMembership


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
