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
    path('chores/', views.chore_list_view, name='chore_list'),
    path('chores/create/', views.chore_create_view, name='chore_create'),
    path('chores/<int:chore_id>/edit/', views.chore_update_view, name='chore_update'),
    path('chores/<int:chore_id>/delete/', views.chore_delete_view, name='chore_delete'),
    path('assignments/<int:assignment_id>/complete/', views.complete_assignment_view, name='complete_assignment'),
    path('history/', views.chore_history_view, name='chore_history'),
    path('notifications/', views.notification_list_view, name='notification_list'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read_view, name='mark_notification_read'),
]
