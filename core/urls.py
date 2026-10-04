"""Core URL Configuration."""
from django.contrib.auth import views as auth_views
from django.urls import include, path
from . import views
from .web import account, chat, legacy_discovery, pilot

# Collaborative Roommate Workspace endpoints (/together/...)
together_patterns = ([
    path("", chat.hub, name="hub"),
    path("discover/", views.modern_discover, name="discover"),
    path("candidate/<int:profile_id>/", views.candidate, name="candidate"),
    path("saved/", views.saved, name="saved"),
    path("compare/", views.compare_candidates, name="compare"),
    path("preferences/", views.preferences, name="preferences"),
    path("chat/<int:conversation_id>/", chat.chat, name="chat"),
    path("chat/<int:conversation_id>/messages/", chat.messages, name="messages"),
    path("chat-with/<int:profile_id>/messages/", chat.pair_messages, name="pair-messages"),
    path("workspace/<int:workspace_id>/", views.workspace, name="workspace"),
    path("workspace/<int:workspace_id>/agreement/", views.agreement, name="agreement"),
    path("rooms/", views.rooms, name="rooms"),
    path("rooms/new/", views.edit_room, name="room-new"),
    path("rooms/compare/", views.compare_rooms, name="room-compare"),
    path("rooms/<int:room_id>/", views.room, name="room"),
    path("rooms/<int:room_id>/edit/", views.edit_room, name="room-edit"),
    path("images/<uuid:image_id>/", views.image, name="image"),
    path("notifications/", views.notifications, name="notifications"),
    path("resume/", views.resume, name="resume"),
    path("action/<str:action>/", views.action, name="action"),
], "journey")

urlpatterns = [
    # Authentication & Account Lifecycle
    path("", views.about, name="home"),
    path("about/", views.about, name="about"),
    path("register/", account.register, name="register"),
    path("login/", account.login_view, name="login"),
    path("logout/", account.logout_view, name="logout"),
    path("password-reset/", auth_views.PasswordResetView.as_view(template_name="registration/password_reset_form.html"), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="registration/password_reset_confirm.html"), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"), name="password_reset_complete"),

    # Profile & Questionnaire
    path("dashboard/", account.dashboard, name="dashboard"),
    path("profile/", account.profile_edit, name="profile_edit"),
    path("profile/avatar/upload/", account.upload_avatar, name="upload_avatar"),
    path("profile/avatar/delete/", account.delete_avatar, name="delete_avatar"),
    path("questionnaire/", account.questionnaire, name="questionnaire"),

    # Collaborative Roommate Workspace
    path("together/", include(together_patterns, namespace="journey")),

    # Legacy Pilot 1 Endpoints
    path("discover/", legacy_discovery.discover, name="discover"),
    path("compare/<int:profile_id>/", legacy_discovery.comparison, name="comparison"),
    path("connect/<int:profile_id>/", legacy_discovery.connect, name="connect"),
    path("connections/<int:request_id>/<str:action>/", legacy_discovery.connection_action, name="connection_action"),
    path("pilot/", pilot.pilot_exercise, name="pilot_exercise"),
    path("staff/pilot/", pilot.pilot_results, name="pilot_results"),
    path("staff/pilot/export/", pilot.pilot_export, name="pilot_export"),
]
