from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from .forms import ChoreForm, HouseholdCreationForm, HouseholdJoinForm, LoginForm, RegisterForm
from .models import Chore, ChoreAssignment, Household, HouseholdMembership
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
    """Protected view placeholder for chore dashboard to verify auth redirection."""
    return render(request, 'home.html', {'is_dashboard': True})


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
