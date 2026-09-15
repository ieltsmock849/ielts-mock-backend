from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import ExamResult
from .serializers import ExamResultSerializer, GradeWritingSerializer
from apps.accounts.permissions import IsOrganizationMember, IsTeacher
from apps.exams.scoring import criteria_to_band, writing_overall_band


class ExamResultViewSet(viewsets.ModelViewSet):
    serializer_class = ExamResultSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ['student', 'exam', 'writing_status']
    search_fields = ['exam_title']

    def get_queryset(self):
        # PERFORMANCE: ExamResultSerializer.get_student_name/get_exam_title_display
        # har bir natija uchun obj.student.name / obj.exam.title'ga murojaat
        # qiladi — select_related bo'lmasa bu har bir yozuv uchun 2 tadan
        # qo'shimcha query (N+1) degani (20 ta natija = 40 ta qo'shimcha
        # so'rov). select_related bittagina JOIN bilan hal qiladi.
        base = ExamResult.objects.select_related('student', 'exam')
        if self.request.user.role == 'support':
            return base
        if self.request.user.role in ['ceo', 'admin']:
            return base.filter(organization_id=self.request.user.organization_id)
        if self.request.user.role == 'student':
            return base.filter(student=self.request.user)
        return ExamResult.objects.none()

    def perform_create(self, serializer):
        serializer.save(
            organization_id=self.request.user.organization_id,
            student=self.request.user if self.request.user.role == 'student' else None
        )

    @action(detail=True, methods=['post'])
    def grade_writing(self, request, pk=None):
        result = self.get_object()

        # Permission check: only staff can grade
        if request.user.role not in ['support', 'ceo', 'admin']:
            return Response({'success': False, 'message': 'Permission denied'},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = GradeWritingSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'message': 'Invalid data', 'errors': serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Calculate bands from criteria if not provided directly
        task1_band = data.get('task1_band')
        task2_band = data.get('task2_band')
        writing_band = data.get('band')

        if not task1_band and data.get('task1_criteria'):
            task1_band = criteria_to_band(data['task1_criteria'])
        if not task2_band and data.get('task2_criteria'):
            task2_band = criteria_to_band(data['task2_criteria'])
        if not writing_band and task1_band is not None and task2_band is not None:
            writing_band = writing_overall_band(task1_band, task2_band)

        result.task1_criteria = data.get('task1_criteria', {})
        result.task2_criteria = data.get('task2_criteria', {})
        result.task1_band = task1_band
        result.task2_band = task2_band
        result.writing_band = writing_band
        result.writing_status = 'graded'

        # Recalculate overall band
        bands = []
        if result.section_bands:
            for k, v in result.section_bands.items():
                if v is not None:
                    bands.append(v)
        if writing_band is not None:
            bands.append(writing_band)
        if bands:
            result.overall_band = round((sum(bands) / len(bands)) * 2) / 2

        result.save()

        return Response({
            'success': True,
            'message': 'Writing graded successfully',
            'data': {
                'task1_band': task1_band,
                'task2_band': task2_band,
                'writing_band': writing_band,
                'overall_band': result.overall_band
            }
        })