from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy

from .forms import HouseholdCreationForm, HouseholdJoinForm, LoginForm, RegisterForm
from .models import Household, HouseholdMembership


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
                HouseholdMembership.objects.create(
                    user=request.user,
                    household=household,
                    is_admin=False
                )
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
            target_membership.delete()
        messages.success(
            request,
            f"{removed_username} was removed from {admin_membership.household.name}."
        )
        return redirect('household_members')

    return render(request, 'household/remove_confirm.html', {
        'household': admin_membership.household,
        'target_membership': target_membership,
    })
