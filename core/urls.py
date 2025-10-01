from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView
app_name = 'core'

urlpatterns = [
    path('', views.group_list_view, name='group_list'),
    path("account/signup/", views.signup_view, name="signup"),
    path("account/login/", views.RememberMeLoginView.as_view(), name="login"),
    path("account/password/reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("account/password/reset/sent/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("account/password/reset/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("account/password/reset/done/", views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("account/logout/", views.logout_view, name="logout"),
    path('groups/', views.group_list_view, name='group_list'),
    path("groups/<slug:slug>/", views.GroupDetailView.as_view(), name="group_detail"),
    path("groups/<slug:slug>/join-request/", views.group_join_request_view, name="group_join_request"),
    path("groups/<slug:slug>/create-join-request/", views.group_create_join_request_view, name="group_create_join_request"),
    path("groups/<slug:slug>/edit/", views.group_edit_view, name="group_edit"),
    path("groups/<slug:slug>/leave/", views.group_leave_view, name="group_leave"),
    path("groups/<slug:slug>/delete/", views.group_delete_view, name="group_delete"),
    path("groups/<slug:slug>/accept-request<int:request_id>/", views.group_accept_request_view, name="group_approve_request"),
    path("groups/<slug:slug>/reject-request<int:request_id>/", views.group_reject_request_view, name="group_reject_request"),
    path("groups/<slug:slug>/promote/<int:user_id>/", views.group_promote_member_view, name="group_promote_member"),
    path("groups/<slug:slug>/demote/<int:user_id>/", views.group_demote_admin_view, name="group_demote_admin"),
    path("groups/<slug:slug>/remove/<int:user_id>/", views.group_remove_member_view, name="group_remove_member"),
    path('create/group', views.group_create_view, name='group_create'),
    path('create/game', views.game_create_view, name='game_create'),
    path('games/<int:pk>/', views.game_detail_view, name='game_detail'),
    path('games/<int:pk>/add-player/', views.participation_add_view, name='participation_add'),
    path("games/<int:pk>/edit/", views.game_edit_view, name="game_edit"),
    path("games/<int:pk>/delete/", views.game_delete_view, name="game_delete"),
    path("games/<int:pk>/participations/<int:part_id>/edit/", views.participation_edit_view, name="participation_edit"),
    path("games/<int:pk>/participations/<int:part_id>/delete/", views.participation_delete_view, name="participation_delete"),

]
