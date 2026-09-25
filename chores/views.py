from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .forms import LoginForm, RegisterForm


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
