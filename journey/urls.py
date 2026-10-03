from django.urls import path
from . import views

app_name = "journey"
urlpatterns = [
    path("", views.hub, name="hub"),
    path("discover/", views.discover, name="discover"),
    path("candidate/<int:profile_id>/", views.candidate, name="candidate"),
    path("saved/", views.saved, name="saved"),
    path("compare/", views.compare_candidates, name="compare"),
    path("preferences/", views.preferences, name="preferences"),
    path("chat/<int:conversation_id>/", views.chat, name="chat"),
    path("chat/<int:conversation_id>/messages/", views.messages, name="messages"),
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
]
