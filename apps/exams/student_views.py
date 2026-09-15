from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from .models import User, Group, Exam, Assignment
from apps.accounts.permissions import IsAdmin, IsTeacher, IsOrganizationMember
from apps.accounts.serializers import UserSerializer


class StudentSerializer(UserSerializer):
    """
    UserSerializer 'role' maydonini majburiy (required) deb hisoblaydi,
    chunki bu maydon Django modelida blank=True/default'siz e'lon qilingan
    (UserViewSet va StaffSerializer buni ataylab talab qiladi — mijoz
    ANIQ rol yuborishi shart). Lekin StudentViewSet.perform_create() rolni
    doim o'zi 'student' qilib belgilaydi va frontend uni umuman yubormaydi
    — shu nomuvofiqlik "role: Bu maydon talab qilinadi" 400 xatosiga olib
    kelardi. Shu sabab faqat shu yerda 'role' ixtiyoriy qilib qo'yiladi.
    """
    class Meta(UserSerializer.Meta):
        extra_kwargs = {**UserSerializer.Meta.extra_kwargs, 'role': {'required': False}}


class StudentViewSet(viewsets.ModelViewSet):
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    search_fields = ['name', 'username']
    filterset_fields = ['group', 'status']

    def get_queryset(self):
        # PERFORMANCE: select_related('group') — UserSerializer.get_group_name/
        # get_group_id har bir student uchun obj.group'ga murojaat qiladi;
        # bo'lmasa bu N+1 query (har bir o'quvchi uchun alohida guruh so'rovi).
        base = User.objects.select_related('group')
        if self.request.user.role == 'support':
            return base.filter(role='student')
        if self.request.user.role in ['ceo', 'admin']:
            return base.filter(
                role='student',
                organization_id=self.request.user.organization_id
            )
        return base.filter(id=self.request.user.id)

    def perform_create(self, serializer):
        # Generate username if not provided
        data = self.request.data
        name = data.get('name', '')
        base = name.strip().lower().replace(' ', '.')
        if not base:
            base = 'student'

        existing = User.objects.filter(username__startswith=base).count()
        username = f"{base}{existing + 1}" if existing else base

        serializer.save(
            role='student',
            username=username,
            organization_id=self.request.user.organization_id
        )

    @action(detail=True, methods=['get'], url_path='password')
    def get_password(self, request, pk=None):
        student = self.get_object()
        if request.user.role not in ['ceo', 'admin', 'support'] and request.user.id != student.id:
            return Response({'success': False, 'message': 'Permission denied'},
                            status=status.HTTP_403_FORBIDDEN)
        return Response({'success': True, 'data': {'password': student.password}})

    @action(detail=True, methods=['put'], url_path='password')
    def set_password(self, request, pk=None):
        student = self.get_object()
        if request.user.role not in ['ceo', 'admin', 'support']:
            return Response({'success': False, 'message': 'Permission denied'},
                            status=status.HTTP_403_FORBIDDEN)

        new_password = request.data.get('password')
        if not new_password:
            return Response({'success': False, 'message': 'Password required'},
                            status=status.HTTP_400_BAD_REQUEST)

        student.set_password(new_password)
        student.save()
        return Response({'success': True, 'message': 'Password updated'})