from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('dashboard/', views.protected_dashboard_view, name='dashboard'),
    path('household/', views.household_members_view, name='household_members'),
    path('household/create/', views.household_create_view, name='household_create'),
    path('household/join/', views.household_join_view, name='household_join'),
    path('household/members/<int:membership_id>/remove/', views.household_remove_member_view, name='household_remove_member'),
]
