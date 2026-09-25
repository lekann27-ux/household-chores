from .models import Notification


def household_context(request):
    """Expose the user's active household and membership to all templates."""
    if request.user.is_authenticated:
        membership = request.user.household_memberships.select_related('household').first()
        household_ids = request.user.household_memberships.values_list('household_id', flat=True)
        unread_notification_count = Notification.objects.filter(
            recipient=request.user,
            household_id__in=household_ids,
            is_read=False,
        ).count()
        return {
            'active_membership': membership,
            'active_household': membership.household if membership else None,
            'unread_notification_count': unread_notification_count,
        }
    return {
        'active_membership': None,
        'active_household': None,
        'unread_notification_count': 0,
    }
