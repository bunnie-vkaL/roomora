from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Message, Profile
from .services import DomainError, conversation_for


@database_sync_to_async
def profile_id_for_user(user_id):
    return Profile.objects.filter(user_id=user_id).values_list("pk", flat=True).first()


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        profile_id = await profile_id_for_user(user.pk)
        if not profile_id:
            await self.close(code=4403)
            return
        self.group_name = f"profile_{profile_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_created(self, event):
        await self.send_json(event["payload"])


@database_sync_to_async
def authorized_conversation(user_id, conversation_id):
    profile = Profile.objects.filter(user_id=user_id).first()
    if not profile:
        return None
    try:
        conversation = conversation_for(profile, conversation_id, allow_pending=True)
    except DomainError:
        return None
    return conversation.pk


@database_sync_to_async
def message_payload(message_id, actor_id):
    message = Message.objects.select_related("sender").filter(pk=message_id).first()
    if not message:
        return None
    return {
        "type": "chat.message",
        "id": message.pk,
        "sender": message.sender.name,
        "sender_id": message.sender_id,
        "mine": message.sender_id == actor_id,
        "body": message.body,
        "created_at": message.created_at.isoformat(),
    }


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        authorized_id = await authorized_conversation(user.pk, conversation_id)
        if not authorized_id:
            await self.close(code=4403)
            return
        self.actor_id = await profile_id_for_user(user.pk)
        self.group_name = f"conversation_{authorized_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def chat_message(self, event):
        payload = await message_payload(event["message_id"], self.actor_id)
        if payload:
            await self.send_json(payload)
