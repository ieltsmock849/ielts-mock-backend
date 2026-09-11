import uuid
from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets, mixins, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import Organization, User
from .models import Message
from .serializers import MessageSerializer
from .realtime import push_to_account

# CEO ostidagi "xodim" rollari (Employee) — Support/CEO/Student bundan tashqari.
# Yangi hiyerarxiyada bu FAQAT "admin" ('teacher'/'manager'/'org_support'
# rollari butunlay olib tashlandi — izoh: apps/accounts/models.py).
STAFF_ROLES = ['admin']


class MessageViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Ichki xabar tizimi:
      - Support -> CEO (barchasiga yoki bittasiga)
      - CEO -> o'z tashkilotidagi Employee (admin/manager/teacher) va Student

    MUHIM (xavfsizlik): standart ModelViewSet o'rniga faqat ListModelMixin
    ishlatilgan — yaratish/o'zgartirish/o'chirish standart /messages/ POST-PUT-
    DELETE orqali EMAS, faqat pastdagi maxsus action'lar (`send`, `respond`)
    orqali, ROL asosidagi qat'iy tekshiruv bilan amalga oshiriladi. Frontend
    tugmalarini yashirish yetarli emas — barcha tekshiruvlar shu yerda,
    backend darajasida takrorlangan.
    """
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'recipient_role']
    search_fields = ['message', 'recipient_name', 'sender_name']

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)

        if role == 'support':
            # Support faqat O'ZI yuborgan xabarlarning statusini ko'radi.
            return Message.objects.filter(sender_role='support', sender_id=user.id)

        if role == 'ceo':
            # CEO: Support'dan kelgan xabarlar (recipient) + o'zi xodim/
            # o'quvchiga yuborgan xabarlar (sender) — ikkalasi ham.
            return Message.objects.filter(
                Q(recipient_role='ceo', recipient_id=user.id) |
                Q(sender_role='ceo', sender_id=user.id)
            )

        if role == 'admin':
            # YANGI: Admin endi CEO bilan BIR XIL — CEO'dan kelgan xabarlar
            # (recipient) + o'zi boshqa xodim/o'quvchiga yuborgan xabarlar
            # (sender) — ikkalasi ham (parity: "CEOda nima bo'lsa, Adminda
            # ham xuddi shunday").
            return Message.objects.filter(
                Q(recipient_role='admin', recipient_id=user.id) |
                Q(sender_role='admin', sender_id=user.id)
            )

        if role == 'student':
            # Student — faqat o'ziga kelgan xabarlar (u xabar yubora olmaydi,
            # faqat qabul qiladi).
            return Message.objects.filter(recipient_role='student', recipient_id=user.id)

        return Message.objects.none()

    @action(detail=False, methods=['get'])
    def unread(self, request):
        """
        Joriy foydalanuvchiga tegishli, hali javob berilmagan (status='sent')
        eng eski xabarni qaytaradi — CEO/Admin/Student dashboard ochilganda
        avtomatik modal ko'rsatish uchun ishlatiladi. Yo'q bo'lsa data: null.
        """
        user = request.user
        role = getattr(user, 'role', None)

        if role in ('ceo', 'admin', 'student'):
            msg = Message.objects.filter(
                recipient_role=role, recipient_id=user.id, status='sent'
            ).order_by('created_at').first()
        else:
            msg = None

        data = MessageSerializer(msg).data if msg else None
        return Response({'success': True, 'data': data})

    @action(detail=False, methods=['post'])
    def send(self, request):
        """
        Xabar yuborish — Support (CEO'larga) yoki CEO/Admin (o'z tashkilotidagi
        Employee/Student'iga, ikkalasi bir xil huquqda). Bir nechta qabul
        qiluvchi bo'lsa, har biriga alohida Message qatori yaratiladi
        (pastga q.: model docstring).
        """
        user = request.user
        role = getattr(user, 'role', None)

        text = (request.data.get('message') or '').strip()
        if not text:
            return Response({'success': False, 'message': 'Xabar matni kiritilishi shart'},
                             status=status.HTTP_400_BAD_REQUEST)

        created = []

        if role == 'support':
            target = request.data.get('target')  # 'all' | 'single'
            if target == 'all':
                recipients = list(Organization.objects.all())
            else:
                org_id = request.data.get('recipient_id')
                org = Organization.objects.filter(id=org_id).first()
                if not org:
                    return Response({'success': False, 'message': 'CEO topilmadi'},
                                     status=status.HTTP_400_BAD_REQUEST)
                recipients = [org]

            if not recipients:
                return Response({'success': False, 'message': "Yuboriladigan CEO topilmadi"},
                                 status=status.HTTP_400_BAD_REQUEST)

            for org in recipients:
                created.append(Message.objects.create(
                    id=f"msg_{uuid.uuid4().hex[:12]}",
                    sender_role='support', sender_id=user.id, sender_name=user.name,
                    recipient_role='ceo', recipient_id=org.id, recipient_name=org.ceo_name,
                    organization=org, message=text,
                ))

        elif role in ('ceo', 'admin'):
            # YANGI: Admin endi CEO bilan BIR XIL huquqda xabar yubora oladi
            # (parity), farqi faqat texnik — CEO uchun request.user aslida
            # Organization obyekti (organization_id = user.id o'zi), Admin
            # uchun esa oddiy User obyekti (organization_id = user.organization_id).
            # MUHIM: CEO/Admin Support'ga yubora olmaydi — bu holat bu yo'l
            # orqali umuman mumkin emas, chunki qabul qiluvchilar faqat
            # so'rovchining O'Z tashkilotidagi User qatorlaridan tanlanadi va
            # Support hech qachon biror Organization'ga bog'lanmagan
            # (Support — alohida platforma darajasidagi User, organization=None).
            org_id = user.id if role == 'ceo' else user.organization_id
            sender_name = user.ceo_name if role == 'ceo' else user.name

            recipient_ids = request.data.get('recipient_ids') or []
            single_id = request.data.get('recipient_id')
            if single_id and single_id not in recipient_ids:
                recipient_ids = [single_id, *recipient_ids]

            if not recipient_ids:
                return Response({'success': False, 'message': 'Qabul qiluvchini tanlang'},
                                 status=status.HTTP_400_BAD_REQUEST)

            # Faqat O'Z tashkilotiga tegishli Employee/Student — boshqa
            # tashkilot yoki Support hech qanday holatda tanlanmaydi.
            users = User.objects.filter(
                id__in=recipient_ids,
                organization_id=org_id,
                role__in=STAFF_ROLES + ['student'],
            )
            found_ids = set(users.values_list('id', flat=True))
            missing = set(recipient_ids) - found_ids
            if missing:
                return Response(
                    {'success': False, 'message': "Ba'zi foydalanuvchilar topilmadi yoki sizning tashkilotingizga tegishli emas"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            for u in users:
                created.append(Message.objects.create(
                    id=f"msg_{uuid.uuid4().hex[:12]}",
                    sender_role=role, sender_id=user.id, sender_name=sender_name,
                    recipient_role=u.role, recipient_id=u.id, recipient_name=u.name,
                    organization_id=org_id, message=text,
                ))

        else:
            return Response({'success': False, 'message': "Bu amal uchun ruxsat yo'q"},
                             status=status.HTTP_403_FORBIDDEN)

        serializer = MessageSerializer(created, many=True)

        # Real-time: har bir qabul qiluvchiga ALOHIDA (o'z Message qatori
        # bilan) darhol yetkazamiz — refreshsiz ko'rinsin.
        for msg, data in zip(created, serializer.data):
            push_to_account(msg.recipient_role, msg.recipient_id, 'new_message', data)

        return Response({'success': True, 'data': serializer.data}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post', 'patch'])
    def respond(self, request, pk=None):
        """
        Xabarni qabul qiluvchining o'zi "O'qilgan" yoki "E'tiborsiz qoldirish"
        deb belgilashi. Faqat AYNAN o'sha xabarning qabul qiluvchisi bosa oladi.
        """
        user = request.user
        role = getattr(user, 'role', None)

        try:
            msg = Message.objects.get(pk=pk)
        except Message.DoesNotExist:
            return Response({'success': False, 'message': 'Xabar topilmadi'},
                             status=status.HTTP_404_NOT_FOUND)

        if not (msg.recipient_role == role and msg.recipient_id == user.id):
            return Response({'success': False, 'message': "Ruxsat yo'q"},
                             status=status.HTTP_403_FORBIDDEN)

        status_val = request.data.get('status')
        if status_val not in ['read', 'ignored']:
            return Response({'success': False, 'message': "Noto'g'ri status"},
                             status=status.HTTP_400_BAD_REQUEST)

        msg.status = status_val
        msg.responded_at = timezone.now()
        msg.save()

        data = MessageSerializer(msg).data
        # Real-time: yuboruvchi ham status ('read'/'ignored') o'zgarganini
        # refreshsiz ko'rsin (masalan Support -> CEO javob berdimi kuzatib
        # turadi).
        push_to_account(msg.sender_role, msg.sender_id, 'message_status_updated', data)
        return Response({'success': True, 'data': data})