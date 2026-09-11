"""
Real-time push yordamchi funksiyalari.

Har qanday view/signal shu yerdagi `push_*` funksiyalaridan birini chaqirib,
tegishli foydalanuvchi(lar)ga WebSocket orqali DARHOL (refreshsiz) xabar
yuboradi. Mavjud REST API va JWT autentifikatsiya tizimiga HECH QANDAY
ta'sir qilmaydi — bu faqat QO'SHIMCHA, "fire-and-forget" kanal.

Guruh nomlash sxemasi (consumers.py'dagi NotificationConsumer shu
guruhlarga a'zo bo'ladi):
  - acct_{role}_{id}  -> bitta aniq hisobning O'ZI (barcha ochiq tablar/
                         qurilmalar birdek oladi)
  - org_{org_id}      -> shu tashkilotning CEO'si + barcha Admin'lari
  - group_{group_id}  -> shu sinf/guruhdagi barcha Student'lar
  - support_all       -> barcha Support xodimlari
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

SUPPORT_GROUP = 'support_all'


def acct_group(role, account_id):
    return f'acct_{role}_{account_id}'


def org_group(org_id):
    return f'org_{org_id}'


def class_group(group_id):
    return f'group_{group_id}'


def _send(group_name, event_type, payload):
    if not group_name:
        return
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(group_name, {
            'type': 'broadcast.event',
            'event': event_type,
            'payload': payload,
        })
    except Exception:
        # Real-time push muvaffaqiyatsiz bo'lsa ham asosiy so'rov (masalan
        # xabar/vazifa yaratish) baribir muvaffaqiyatli yakunlanishi kerak —
        # shu sabab bu yerda xatolik yutiladi, faqat log yoziladi.
        logger.exception("Realtime push failed: group=%s event=%s", group_name, event_type)


def push_to_account(role, account_id, event_type, payload):
    """Bitta aniq foydalanuvchi (yoki CEO uchun Organization)ga yuborish."""
    _send(acct_group(role, account_id), event_type, payload)


def push_to_org(org_id, event_type, payload):
    """Tashkilotning CEO'si va barcha Admin'lariga yuborish."""
    _send(org_group(org_id), event_type, payload)


def push_to_class_group(group_id, event_type, payload):
    """Bitta sinf/guruhdagi barcha Student'larga yuborish."""
    _send(class_group(group_id), event_type, payload)


def push_to_support(event_type, payload):
    """Barcha Support xodimlariga yuborish."""
    _send(SUPPORT_GROUP, event_type, payload)
