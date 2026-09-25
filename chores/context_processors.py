def household_context(request):
    """Expose the user's active household and membership to all templates."""
    if request.user.is_authenticated:
        membership = request.user.household_memberships.select_related('household').first()
        return {
            'active_membership': membership,
            'active_household': membership.household if membership else None,
        }
    return {
        'active_membership': None,
        'active_household': None,
    }
