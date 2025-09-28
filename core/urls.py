from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView

app_name = 'core'

urlpatterns = [
    path('', views.group_list_view, name='group_list'),
    path("account/signup/", views.signup_view, name="signup"),
    path("account/login/", views.RememberMeLoginView.as_view(), name="login"),
    path("account/logout/", views.logout_view, name="logout"),
    path('groups/', views.group_list_view, name='group_list'),
    path("groups/<slug:slug>/", views.GroupDetailView.as_view(), name="group_detail"),
    path("groups/<slug:slug>/join-request/", views.group_join_request_view, name="group_join_request"),
    path("groups/<slug:slug>/create-join-request/", views.group_create_join_request_view, name="group_create_join_request"),
    path("groups/<slug:slug>/leave/", views.group_leave_view, name="group_leave"),
    path("groups/<slug:slug>/delete/", views.group_delete_view, name="group_delete"),
    path("groups/<slug:slug>/accept-request<int:request_id>/", views.group_accept_request_view, name="group_approve_request"),
    path("groups/<slug:slug>/reject-request<int:request_id>/", views.group_reject_request_view, name="group_reject_request"),
    path('create/group', views.group_create_view, name='group_create'),
    path('create/game', views.game_create_view, name='game_create'),
    path('games/<int:pk>/', views.game_detail_view, name='game_detail'),
    path('games/<int:pk>/add-player/', views.participation_add_view, name='participation_add'),
]
