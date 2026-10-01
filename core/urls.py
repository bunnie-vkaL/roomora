from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
from .forms import EmailAuthenticationForm

urlpatterns = [
    path("", views.home, name="home"), path("register/", views.register, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html", authentication_form=EmailAuthenticationForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password-reset/", auth_views.PasswordResetView.as_view(template_name="registration/password_reset_form.html"), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="registration/password_reset_confirm.html"), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"), name="password_reset_complete"),
    path("dashboard/", views.dashboard, name="dashboard"), path("profile/", views.profile_edit, name="profile_edit"),
    path("profile/avatar/upload/", views.upload_avatar, name="upload_avatar"),
    path("profile/avatar/delete/", views.delete_avatar, name="delete_avatar"),
    path("questionnaire/", views.questionnaire, name="questionnaire"),
    path("discover/", views.discover, name="discover"), path("compare/<int:profile_id>/", views.comparison, name="comparison"), path("connect/<int:profile_id>/", views.connect, name="connect"),
    path("connections/<int:request_id>/<str:action>/", views.connection_action, name="connection_action"), path("pilot/", views.pilot_exercise, name="pilot_exercise"),
    path("staff/pilot/", views.pilot_results, name="pilot_results"), path("staff/pilot/export/", views.pilot_export, name="pilot_export"),
]
