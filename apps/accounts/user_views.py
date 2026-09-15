from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from .models import User
from .serializers import UserSerializer
from .permissions import IsSupport, IsAdmin, IsOrganizationMember

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    search_fields = ['name', 'username']
    filterset_fields = ['role', 'status', 'group']

    def get_queryset(self):
        # PERFORMANCE: select_related('group') — izoh: student_views.py.
        base = User.objects.select_related('group')
        if self.request.user.role == 'support':
            return base
        return base.filter(organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        serializer.save(organization_id=self.request.user.organization_id)

    def perform_update(self, serializer):
        # MUHIM: 'support' roliga ega hech qanday yozuvni HECH KIM (o'zi ham)
        # bu (yoki boshqa) endpoint orqali tahrirlay olmaydi. Bu klass Support
        # uchun get_queryset() orqali BARCHA userlarni (jumladan boshqa
        # 'support' yozuvlarini) qaytargani uchun, shu himoya bo'lmasa Support
        # o'zini yoki boshqa Support hisobini o'zgartirib qo'yishi mumkin edi.
        if serializer.instance.role == 'support':
            raise PermissionDenied("Support hisobini hech kim tahrirlay olmaydi.")
        serializer.save()

    def perform_destroy(self, instance):
        # Xuddi shu sabab bilan — 'support' yozuvini hech kim o'chira olmaydi.
        if instance.role == 'support':
            raise PermissionDenied("Support hisobini hech kim o'chira olmaydi.")
        instance.delete()

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = UserSerializer(request.user)
        return Response({'success': True, 'data': serializer.data})