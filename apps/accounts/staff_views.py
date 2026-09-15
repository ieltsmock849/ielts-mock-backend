from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, BasePermission
from .models import User
from .serializers import StaffSerializer

class IsCeoOrSupport(BasePermission):
    """
    YANGILANDI (qaytarildi): Xodimlarni (Admin hisoblarini) TO'LIQ boshqarish
    — ro'yxatni ko'rish, yaratish, boshqa xodimni tahrirlash/o'chirish —
    FAQAT CEO (o'z tashkilotiga) va Support (istalgan tashkilotga) uchun.
    "Xodimlar" endi Admin uchun mavjud emas (frontendda ham tab butunlay
    yashirilgan, izoh: index.html/AdminApp).

    MUHIM ISTISNO: Admin baribir shu endpoint orqali FAQAT O'Z profilini
    (ism/telefon/avatar/parol) yangilay olishi kerak — chunki "Profil"
    sahifasi buni ishlatadi (frontendda "Xodimlar" bo'limi yo'qligidan
    qat'iy nazar, shaxsiy profilni tahrirlash alohida, umumiy imkoniyat).
    Shu sabab PATCH/PUT (update/partial_update) uchun Admin'ga view
    darajasida yo'l beriladi, lekin OBYEKT darajasida (has_object_permission)
    faqat AYNAN O'Z yozuviga ruxsat beriladi — boshqa birorta ham emas.
    """
    def has_permission(self, request, view):
        if request.user and request.user.role in ('ceo', 'support'):
            return True
        # Admin uchun: PATCH/PUT bilan bir qatorda 'list'/'retrieve' ham
        # zarur — chunki frontend "Profil" sahifasida avval ro'yxatdan
        # o'z yozuvini topadi (staffApi.list() -> find), keyin shuni
        # yangilaydi. Bular bo'lmasa GET /api/staff/ Admin uchun 403
        # qaytarib, natijada frontend'da "existing" topilmay, self-edit
        # ham "ruxsat yo'q" bilan rad etilib qolar edi. get_queryset()
        # baribir faqat O'Z tashkilotidagi admin'larni qaytaradi, va
        # has_object_permission pastda faqat AYNAN o'z yozuvini tahrirlash/
        # o'chirishga ruxsat beradi — xavfsizlik shu bilan saqlanadi.
        if request.user and request.user.role == 'admin' and view.action in ('update', 'partial_update', 'list', 'retrieve'):
            return True
        return False

    def has_object_permission(self, request, view, obj):
        if request.user.role in ('ceo', 'support'):
            return True
        if request.user.role == 'admin':
            return obj.id == request.user.id
        return False

# Xodim (organization employee) darajasidagi yagona rol — endi faqat 'admin'.
# ('teacher'/'manager'/'org_support' rollari butunlay olib tashlandi;
# 0005_migrate_legacy_roles_to_admin migratsiyasi mavjud bazadagi bunday
# yozuvlarni ham "admin"ga o'tkazgan, shu sabab bu yerda ularni alohida
# hisobga olishning hojati yo'q.)
STAFF_ROLES = ['admin']

class StaffViewSet(viewsets.ModelViewSet):
    serializer_class = StaffSerializer
    permission_classes = [IsAuthenticated, IsCeoOrSupport]
    search_fields = ['name', 'username']
    filterset_fields = ['role', 'status']

    def get_queryset(self):
        # MUHIM: 'support' roli bu yerda ATAYLAB STAFF_ROLES'ga kiritilmagan —
        # shu sabab Support hisoblari bu ro'yxatda (demak update/destroy orqali
        # ham) HECH QACHON ko'rinmaydi, hatto boshqa Support foydalanuvchisi
        # so'rasa ham ("Support accountini hech kim o'zgartira/o'chira olmasin").
        # PERFORMANCE: select_related('group') — izoh: student_views.py.
        base = User.objects.select_related('group')
        if self.request.user.role == 'support':
            return base.filter(role__in=STAFF_ROLES)
        return base.filter(
            role__in=STAFF_ROLES,
            organization_id=self.request.user.organization_id
        )

    def perform_create(self, serializer):
        # CEO — doim FAQAT o'z tashkilotiga xodim qo'sha oladi (xavfsizlik
        # uchun so'rovdan kelgan "organization" qiymati e'tiborga olinmaydi).
        # Support — istalgan tashkilotga xodim qo'sha oladi, lekin qaysi
        # tashkilotga tegishli ekanligi so'rovda ANIQ ko'rsatilishi shart.
        if self.request.user.role == 'support':
            org_id = self.request.data.get('organization') or self.request.data.get('orgId')
            serializer.save(organization_id=org_id)
        else:
            serializer.save(organization_id=self.request.user.organization_id)

    @action(detail=True, methods=['patch'])
    def status(self, request, pk=None):
        staff = self.get_object()
        status_val = request.data.get('status')
        if status_val not in ['active', 'inactive']:
            return Response({'success': False, 'message': 'Invalid status'},
                          status=status.HTTP_400_BAD_REQUEST)
        staff.status = status_val
        staff.save()
        return Response({'success': True, 'status': staff.status})