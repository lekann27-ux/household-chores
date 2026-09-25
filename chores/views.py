from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from .forms import (
    AssignmentHistoryFilterForm,
    ChoreForm,
    HouseholdCreationForm,
    HouseholdJoinForm,
    LoginForm,
    RegisterForm,
)
from .models import (
    Chore,
    ChoreAssignment,
    ChoreRotationMember,
    Household,
    HouseholdMembership,
    Notification,
)
from .services.assignments import complete_assignment
from .services.members import remove_member_from_household
from .services.rotation import (
    enroll_member_in_active_chore_rotations,
    initialize_chore_rotation,
)


def home_view(request):
    """Landing page for guests, welcome view for authenticated users."""
    return render(request, 'home.html')


def register_view(request):
    """Handle new user registration."""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                "Your account has been created successfully! Please sign in."
            )
            return redirect('login')
    else:
        form = RegisterForm()

    return render(request, 'auth/register.html', {'form': form})


class CustomLoginView(LoginView):
    """Custom login view utilizing styled LoginForm and feedback messages."""
    authentication_form = LoginForm
    template_name = 'auth/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Welcome back, {self.request.user.username}!")
        return response


class CustomLogoutView(LogoutView):
    """Custom logout view providing flash message and flexible dispatch."""
    next_page = reverse_lazy('login')
    http_method_names = ['get', 'post', 'options']

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.info(request, "You have been logged out.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        """Allow GET request to trigger logout for user convenience."""
        return self.post(request, *args, **kwargs)


@login_required
def protected_dashboard_view(request):
    """Show the current user's assignments and each household's active chores."""
    memberships = list(
        request.user.household_memberships.select_related('household').order_by('pk')
    )
    membership_ids = [membership.pk for membership in memberships]
    household_ids = [membership.household_id for membership in memberships]
    today = timezone.localdate()

    active_assignments = list(
        ChoreAssignment.objects.filter(
            chore__household_id__in=household_ids,
            status__in=(ChoreAssignment.Status.PENDING, ChoreAssignment.Status.OVERDUE),
        )
        .select_related('chore__household', 'assigned_to__user')
        .order_by('due_date', 'chore__title', 'pk')
    )
    for assignment in active_assignments:
        assignment.display_status = assignment.status
        if (
            assignment.status == ChoreAssignment.Status.PENDING
            and assignment.due_date < today
        ):
            # Show overdue urgency immediately; the scheduled scanner persists
            # this state without changing the assignee or advancing rotation.
            assignment.display_status = ChoreAssignment.Status.OVERDUE
        assignment.can_complete = (
            assignment.assigned_to.user_id == request.user.pk
            or assignment.chore.household.admin_id == request.user.pk
        )

    my_assignments = [
        assignment for assignment in active_assignments
        if assignment.assigned_to_id in membership_ids
        and assignment.assigned_to.user_id == request.user.pk
    ]
    my_overdue = [
        assignment for assignment in my_assignments
        if assignment.display_status == ChoreAssignment.Status.OVERDUE
    ]
    my_due_today = [
        assignment for assignment in my_assignments
        if assignment.display_status == ChoreAssignment.Status.PENDING
        and assignment.due_date == today
    ]
    my_upcoming = [
        assignment for assignment in my_assignments
        if assignment.display_status == ChoreAssignment.Status.PENDING
        and assignment.due_date > today
    ]

    current_assignment_queryset = (
        ChoreAssignment.objects.filter(
            status__in=(ChoreAssignment.Status.PENDING, ChoreAssignment.Status.OVERDUE),
        )
        .select_related('assigned_to__user')
        .order_by('due_date', 'pk')
    )
    rotation_queryset = ChoreRotationMember.objects.select_related('membership__user').order_by(
        'sequence_order', 'pk',
    )
    household_chores = list(
        Chore.objects.filter(household_id__in=household_ids, is_active=True)
        .select_related('household')
        .prefetch_related(
            Prefetch('assignments', queryset=current_assignment_queryset, to_attr='active_assignments'),
            Prefetch('rotation_members', queryset=rotation_queryset, to_attr='ordered_rotation'),
        )
        .order_by('household__name', 'title', 'pk')
    )

    upcoming_rotations = []
    for chore in household_chores:
        chore.current_assignment = chore.active_assignments[0] if chore.active_assignments else None
        if chore.current_assignment:
            chore.current_assignment.display_status = chore.current_assignment.status
            if (
                chore.current_assignment.status == ChoreAssignment.Status.PENDING
                and chore.current_assignment.due_date < today
            ):
                chore.current_assignment.display_status = ChoreAssignment.Status.OVERDUE
            current_index = next(
                (
                    index for index, rotation in enumerate(chore.ordered_rotation)
                    if rotation.membership_id == chore.current_assignment.assigned_to_id
                ),
                None,
            )
            if current_index is None or not chore.ordered_rotation:
                chore.next_member = None
            else:
                next_rotation = chore.ordered_rotation[
                    (current_index + 1) % len(chore.ordered_rotation)
                ]
                chore.next_member = next_rotation.membership
            upcoming_rotations.append(chore)
        else:
            chore.next_member = None

    recent_completed = list(
        ChoreAssignment.objects.filter(
            chore__household_id__in=household_ids,
            status=ChoreAssignment.Status.COMPLETED,
        )
        .select_related('chore__household', 'assigned_to__user', 'completed_by__user')
        .order_by('-completed_at', '-pk')[:5]
    )
    for assignment in recent_completed:
        assignment.display_status = ChoreAssignment.Status.COMPLETED

    return render(request, 'chores/dashboard.html', {
        'households': [membership.household for membership in memberships],
        'my_overdue': my_overdue,
        'my_due_today': my_due_today,
        'my_upcoming': my_upcoming,
        'all_household_chores': household_chores,
        'upcoming_rotations': upcoming_rotations,
        'recent_completed': recent_completed,
        'today': today,
    })


@login_required
def household_create_view(request):
    """Create a new household and assign creator as administrator."""
    if request.user.household_memberships.exists():
        messages.info(request, "You already belong to a household.")
        return redirect('household_members')

    if request.method == 'POST':
        form = HouseholdCreationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                household = form.save(commit=False)
                household.admin = request.user
                household.save()
                HouseholdMembership.objects.create(
                    user=request.user,
                    household=household,
                    is_admin=True
                )
            messages.success(
                request,
                f"Household '{household.name}' created! Share code {household.join_code} with your housemates."
            )
            return redirect('household_members')
    else:
        form = HouseholdCreationForm()

    return render(request, 'household/create.html', {'form': form})


@login_required
def household_join_view(request):
    """Join an existing household using an invite join code."""
    if request.user.household_memberships.exists():
        messages.info(request, "You already belong to a household.")
        return redirect('household_members')

    if request.method == 'POST':
        form = HouseholdJoinForm(request.POST)
        if form.is_valid():
            join_code = form.cleaned_data['join_code']
            household = Household.objects.get(join_code=join_code)
            with transaction.atomic():
                membership = HouseholdMembership.objects.create(
                    user=request.user,
                    household=household,
                    is_admin=False
                )
                enroll_member_in_active_chore_rotations(membership)
            messages.success(
                request,
                f"Welcome to {household.name}! You have joined the household."
            )
            return redirect('household_members')
    else:
        form = HouseholdJoinForm()

    return render(request, 'household/join.html', {'form': form})


@login_required
def household_members_view(request):
    """Display the household member roster and administrative options."""
    membership = request.user.household_memberships.select_related('household').first()
    if not membership:
        messages.info(
            request,
            "You are not a member of any household yet. Create one or join with an invite code."
        )
        return redirect('household_create')

    household = membership.household
    members = household.memberships.select_related('user').order_by('-is_admin', 'joined_at')

    is_admin = household.admin_id == request.user.id
    return render(request, 'household/members.html', {
        'household': household,
        'members': members,
        'current_membership': membership,
        'is_admin': is_admin,
    })


@login_required
def household_remove_member_view(request, membership_id):
    """Allow household administrator to remove a non-admin member."""
    admin_membership = request.user.household_memberships.select_related('household').first()
    if not admin_membership or admin_membership.household.admin_id != request.user.id:
        return HttpResponseForbidden("Only household administrators can remove members.")

    target_membership = get_object_or_404(
        HouseholdMembership.objects.select_related('user'),
        id=membership_id,
        household=admin_membership.household
    )

    if (
        target_membership.user_id == admin_membership.household.admin_id
        or target_membership.is_admin
    ):
        messages.error(request, "The household administrator cannot be removed.")
        return redirect('household_members')

    if request.method == 'POST':
        removed_username = target_membership.user.username
        with transaction.atomic():
            remove_member_from_household(target_membership, request.user)
        messages.success(
            request,
            f"{removed_username} was removed from {admin_membership.household.name}."
        )
        return redirect('household_members')

    return render(request, 'household/remove_confirm.html', {
        'household': admin_membership.household,
        'target_membership': target_membership,
    })


def _chore_membership_or_redirect(request):
    membership = request.user.household_memberships.select_related('household').first()
    if membership is None:
        messages.info(request, 'Join or create a household before managing chores.')
        return None, redirect('household_create')
    return membership, None


def _is_household_admin(request, membership):
    return membership.household.admin_id == request.user.id


@login_required
def chore_list_view(request):
    """List chores for the current user's household."""
    membership, response = _chore_membership_or_redirect(request)
    if response:
        return response

    household = membership.household
    return render(request, 'chores/list.html', {
        'household': household,
        'chores': Chore.objects.filter(household=household),
        'is_admin': _is_household_admin(request, membership),
    })


@login_required
def chore_create_view(request):
    """Create a chore within the current household (admin only)."""
    membership, response = _chore_membership_or_redirect(request)
    if response:
        return response
    if not _is_household_admin(request, membership):
        return HttpResponseForbidden('Only household administrators can manage chores.')

    if request.method == 'POST':
        form = ChoreForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                chore = form.save(commit=False)
                chore.household = membership.household
                chore.save()
                initialize_chore_rotation(chore, timezone.localdate())
            messages.success(request, f'Chore "{chore.title}" was created.')
            return redirect('chore_list')
    else:
        form = ChoreForm()

    return render(request, 'chores/form.html', {
        'form': form,
        'household': membership.household,
        'page_title': 'Create Chore',
        'submit_label': 'Create Chore',
    })


@login_required
def chore_update_view(request, chore_id):
    """Edit a chore only when it belongs to the admin's household."""
    membership, response = _chore_membership_or_redirect(request)
    if response:
        return response
    if not _is_household_admin(request, membership):
        return HttpResponseForbidden('Only household administrators can manage chores.')

    chore = get_object_or_404(Chore, pk=chore_id, household=membership.household)
    if request.method == 'POST':
        form = ChoreForm(request.POST, instance=chore)
        if form.is_valid():
            form.save()
            messages.success(request, f'Chore "{chore.title}" was updated.')
            return redirect('chore_list')
    else:
        form = ChoreForm(instance=chore)

    return render(request, 'chores/form.html', {
        'form': form,
        'household': membership.household,
        'chore': chore,
        'page_title': 'Edit Chore',
        'submit_label': 'Save Changes',
    })


@login_required
def chore_delete_view(request, chore_id):
    """Confirm and delete a chore owned by the current household (admin only)."""
    membership, response = _chore_membership_or_redirect(request)
    if response:
        return response
    if not _is_household_admin(request, membership):
        return HttpResponseForbidden('Only household administrators can manage chores.')

    chore = get_object_or_404(Chore, pk=chore_id, household=membership.household)
    if request.method == 'POST':
        title = chore.title
        chore.delete()
        messages.success(request, f'Chore "{title}" was deleted.')
        return redirect('chore_list')

    return render(request, 'chores/delete_confirm.html', {
        'chore': chore,
        'household': membership.household,
    })


@login_required
def complete_assignment_view(request, assignment_id):
    """Complete a household assignment via POST as its assignee or admin."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    membership = request.user.household_memberships.select_related('household').first()
    if membership is None:
        return HttpResponseForbidden('You must belong to the chore household to complete it.')

    assignment = get_object_or_404(
        ChoreAssignment,
        pk=assignment_id,
        chore__household=membership.household,
    )
    try:
        complete_assignment(assignment.pk, membership)
    except PermissionDenied as exc:
        return HttpResponseForbidden(str(exc))
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect('chore_list')

    messages.success(request, f'"{assignment.chore.title}" was marked complete.')
    return redirect('chore_list')


@login_required
def chore_history_view(request):
    """Browse completed assignments limited to the user's household memberships."""
    memberships = request.user.household_memberships.select_related('household', 'user')
    household_ids = list(memberships.values_list('household_id', flat=True))
    chores = Chore.objects.filter(household_id__in=household_ids).order_by('title', 'pk')
    household_members = HouseholdMembership.objects.filter(
        household_id__in=household_ids,
    ).select_related('household', 'user').order_by('household__name', 'user__username', 'pk')
    form = AssignmentHistoryFilterForm(
        request.GET or None,
        chores=chores,
        memberships=household_members,
    )

    assignments = ChoreAssignment.objects.filter(
        chore__household_id__in=household_ids,
        status=ChoreAssignment.Status.COMPLETED,
    ).select_related(
        'chore__household', 'assigned_to__user', 'completed_by__user',
    ).order_by('-completed_at', '-pk')

    if form.is_valid():
        chore = form.cleaned_data.get('chore')
        member = form.cleaned_data.get('member')
        date_from = form.cleaned_data.get('date_from')
        date_to = form.cleaned_data.get('date_to')
        if chore:
            assignments = assignments.filter(chore=chore)
        if member:
            assignments = assignments.filter(completed_by=member)
        if date_from:
            assignments = assignments.filter(completed_at__date__gte=date_from)
        if date_to:
            assignments = assignments.filter(completed_at__date__lte=date_to)

    paginator = Paginator(assignments, 25)
    history_page = paginator.get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    query_params.pop('page', None)

    return render(request, 'chores/history.html', {
        'form': form,
        'history_page': history_page,
        'querystring': query_params.urlencode(),
    })


@login_required
def notification_list_view(request):
    """Show only notifications for the signed-in user and current households."""
    household_ids = request.user.household_memberships.values_list('household_id', flat=True)
    notifications = Notification.objects.filter(
        recipient=request.user,
        household_id__in=household_ids,
    ).select_related('household', 'assignment__chore').order_by('-created_at', '-pk')
    page = Paginator(notifications, 25).get_page(request.GET.get('page'))
    return render(request, 'chores/notifications.html', {'notification_page': page})


@login_required
def mark_notification_read_view(request, notification_id):
    """Mark one of the current user's household notifications as read."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    household_ids = request.user.household_memberships.values_list('household_id', flat=True)
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        recipient=request.user,
        household_id__in=household_ids,
    )
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=['is_read'])
    return redirect('notification_list')
