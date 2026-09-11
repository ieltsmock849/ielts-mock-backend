"""
Yagona real-time WebSocket kanal.

Har bir rol (CEO, Support, Admin, Teacher/Manager -> Admin, Student) login
qilgandan keyin shu consumer'ga ulanadi va o'ziga tegishli channel-layer
guruh(lar)iga a'zo bo'ladi (realtime.py'dagi nomlash sxemasi). Backend'ning
istalgan joyidan (views.py, signals.py) shu guruhlarga yuborilgan har qanday
event ulangan HAMMA tab/qurilmaga bir zumda yetadi — frontend'ga refresh
kerak emas.
"""
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .realtime import SUPPORT_GROUP, acct_group, class_group, org_group


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if user is None or not getattr(user, 'is_authenticated', False):
            await self.close(code=4401)
            return

        role = getattr(user, 'role', None)
        self.group_names = [acct_group(role, user.id)]

        if role == 'ceo':
            # CEO uchun request.user.id == o'z tashkiloti id'si.
            self.group_names.append(org_group(user.id))
        elif role == 'admin':
            org_id = getattr(user, 'organization_id', None)
            if org_id:
                self.group_names.append(org_group(org_id))
        elif role == 'student':
            group_id = getattr(user, 'group_id', None)
            if group_id:
                self.group_names.append(class_group(group_id))
        elif role == 'support':
            self.group_names.append(SUPPORT_GROUP)

        for group_name in self.group_names:
            await self.channel_layer.group_add(group_name, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        for group_name in getattr(self, 'group_names', []):
            await self.channel_layer.group_discard(group_name, self.channel_name)

    # group_send({'type': 'broadcast.event', ...}) -> Channels 'type'dagi
    # nuqtani pastki chiziqqa aylantirib, shu metodni chaqiradi.
    async def broadcast_event(self, event):
        await self.send_json({
            'event': event['event'],
            'payload': event['payload'],
        })

    async def receive_json(self, content, **kwargs):
        # Ulanishni "tirik" ushlab turish uchun oddiy ping/pong. Frontend
        # hozircha buni yubormasa ham bo'ladi — bu faqat kelajak uchun
        # zararsiz asos (masalan uzoq muddat ochiq turadigan proxy'lar
        # bo'sh WS ulanishlarni yopib qo'ymasligi uchun).
        if content.get('type') == 'ping':
            await self.send_json({'event': 'pong'})
