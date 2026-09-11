from channels.testing import WebsocketCommunicator
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Organization, User
from apps.exams.models import Group
from config.asgi import application

from asgiref.sync import sync_to_async

from .realtime import push_to_account, push_to_class_group, push_to_org, push_to_support


def make_access_token(user_id, role):
    refresh = RefreshToken()
    refresh['user_id'] = user_id
    refresh['role'] = role
    return str(refresh.access_token)


class RealtimeNotificationTests(TestCase):
    """
    NotificationConsumer + JWTAuthMiddleware + realtime push funksiyalarini
    uchidan-uchiga (end-to-end) tekshiradi: token bilan ulanish, guruhlarga
    a'zo bo'lish va group_send orqali kelgan event'ni WS ulanish orqali olish.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            id='org_1', org_name='Test Org', ceo_name='Test CEO',
            username='ceo_test', password='x',
        )
        self.group = Group.objects.create(id='grp_1', organization=self.org, name='A1', level='B1')
        self.student = User.objects.create(
            id='stu_1', organization=self.org, name='Student One',
            username='student1', password='x', role='student', group=self.group,
        )
        self.support = User.objects.create(
            id='sup_1', name='Support One', username='support1', password='x', role='support',
        )

    async def test_unauthenticated_connection_is_rejected(self):
        communicator = WebsocketCommunicator(application, '/ws/notifications/')
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_invalid_token_is_rejected(self):
        communicator = WebsocketCommunicator(application, '/ws/notifications/?token=not-a-real-token')
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_student_receives_new_exam_pushed_to_their_class_group(self):
        token = make_access_token(self.student.id, 'student')
        communicator = WebsocketCommunicator(application, f'/ws/notifications/?token={token}')
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await sync_to_async(push_to_class_group)(self.group.id, 'new_exam', {'id': 'exam_1', 'title': 'Mock Exam 1'})

        message = await communicator.receive_json_from(timeout=5)
        self.assertEqual(message['event'], 'new_exam')
        self.assertEqual(message['payload']['id'], 'exam_1')

        await communicator.disconnect()

    async def test_student_receives_personal_message(self):
        token = make_access_token(self.student.id, 'student')
        communicator = WebsocketCommunicator(application, f'/ws/notifications/?token={token}')
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await sync_to_async(push_to_account)('student', self.student.id, 'new_message', {'id': 'msg_1', 'message': 'Salom'})

        message = await communicator.receive_json_from(timeout=5)
        self.assertEqual(message['event'], 'new_message')
        self.assertEqual(message['payload']['message'], 'Salom')

        await communicator.disconnect()

    async def test_ceo_receives_org_broadcast(self):
        token = make_access_token(self.org.id, 'ceo')
        communicator = WebsocketCommunicator(application, f'/ws/notifications/?token={token}')
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await sync_to_async(push_to_org)(self.org.id, 'new_support_ticket', {'id': 'tkt_1'})

        message = await communicator.receive_json_from(timeout=5)
        self.assertEqual(message['event'], 'new_support_ticket')

        await communicator.disconnect()

    async def test_support_agent_receives_broadcast_to_all_support(self):
        token = make_access_token(self.support.id, 'support')
        communicator = WebsocketCommunicator(application, f'/ws/notifications/?token={token}')
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await sync_to_async(push_to_support)('new_support_ticket', {'id': 'tkt_2'})

        message = await communicator.receive_json_from(timeout=5)
        self.assertEqual(message['event'], 'new_support_ticket')

        await communicator.disconnect()

    async def test_student_does_not_receive_other_groups_events(self):
        other_group = await self._create_other_group()
        token = make_access_token(self.student.id, 'student')
        communicator = WebsocketCommunicator(application, f'/ws/notifications/?token={token}')
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await sync_to_async(push_to_class_group)(other_group.id, 'new_exam', {'id': 'exam_other'})

        with self.assertRaises(TimeoutError):
            # timeout ichida hech narsa kelmasligi kerak (boshqa guruhga tegishli)
            await communicator.receive_json_from(timeout=1)

    async def _create_other_group(self):
        from channels.db import database_sync_to_async
        return await database_sync_to_async(Group.objects.create)(
            id='grp_2', organization=self.org, name='B1', level='B2'
        )
