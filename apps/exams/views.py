from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from django.utils import timezone
from .models import Group, Exam, Assignment, ExamAttempt
from .serializers import GroupSerializer, ExamSerializer, AssignmentSerializer, ExamAttemptSerializer
from apps.accounts.permissions import IsSupport, IsAdmin, IsManager, IsTeacher, IsStudent, IsOrganizationMember
from rest_framework.permissions import IsAuthenticated
from .scoring import is_answer_correct, has_answer
from apps.notifications.realtime import push_to_class_group
import uuid


class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ['level']
    search_fields = ['name']

    def get_queryset(self):
        if self.request.user.role == 'support':
            return Group.objects.all()
        if self.request.user.role in ['ceo', 'admin']:
            return Group.objects.filter(organization_id=self.request.user.organization_id)
        return Group.objects.none()

    def perform_create(self, serializer):
        serializer.save(organization_id=self.request.user.organization_id)


class ExamViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    search_fields = ['title']
    filterset_fields = ['status', 'exam_type']

    def get_queryset(self):
        if self.request.user.role == 'support':
            return Exam.objects.all()
        if self.request.user.role in ['ceo', 'admin']:
            return Exam.objects.filter(organization_id=self.request.user.organization_id)
        if self.request.user.role == 'student':
            return Exam.objects.filter(
                status='on',
                assigned_groups__in=[self.request.user.group_id],
                organization_id=self.request.user.organization_id
            )
        return Exam.objects.none()

    def perform_create(self, serializer):
        exam = serializer.save(organization_id=self.request.user.organization_id)
        # Set assigned groups
        assigned_groups = self.request.data.get('assigned_groups', [])
        if assigned_groups:
            exam.assigned_groups.set(assigned_groups)

        # Real-time: mock exam faol ('on') bo'lib yaratilsa, tayinlangan
        # guruh(lar)dagi barcha Student'larga darhol yetkaziladi.
        if exam.status == 'on':
            data = ExamSerializer(exam).data
            for group_id in assigned_groups:
                push_to_class_group(group_id, 'new_exam', data)

    @action(detail=True, methods=['patch'])
    def toggle(self, request, pk=None):
        exam = self.get_object()
        exam.status = 'off' if exam.status == 'on' else 'on'
        exam.save()

        if exam.status == 'on':
            data = ExamSerializer(exam).data
            for group in exam.assigned_groups.all():
                push_to_class_group(group.id, 'new_exam', data)

        return Response({'success': True, 'status': exam.status})

    @action(detail=True, methods=['patch'])
    def reopen(self, request, pk=None):
        exam = self.get_object()
        exam.status = 'on'
        exam.reopened_at = timezone.now()
        exam.notif_seen_by.clear()
        exam.save()

        # Real-time: qayta ochilgan exam ham "yangi" sifatida darhol
        # ko'rinsin (notif_seen_by tozalanganiga mos).
        data = ExamSerializer(exam).data
        for group in exam.assigned_groups.all():
            push_to_class_group(group.id, 'new_exam', data)

        return Response({'success': True, 'message': 'Exam reopened'})

    @action(detail=True, methods=['get'])
    def start(self, request, pk=None):
        exam = self.get_object()
        student = request.user

        # Check if there's an existing in-progress attempt
        attempt = ExamAttempt.objects.filter(
            student=student,
            exam=exam,
            status='in_progress'
        ).first()

        if not attempt:
            attempt = ExamAttempt.objects.create(
                id=f"att_{uuid.uuid4().hex[:8]}",
                student=student,
                exam=exam,
                answers={section: {} for section in ['listening', 'reading', 'vocabulary']},
                writing_text={'task1': '', 'task2': ''},
                flagged={},
                notepad_text='',
                font_level=1,
                section_deadlines={},
                progress_data={}
            )

        serializer = ExamAttemptSerializer(attempt)
        return Response({'success': True, 'data': {
            'attempt': serializer.data,
            'exam': ExamSerializer(exam).data
        }})

    @action(detail=True, methods=['post'])
    def save_progress(self, request, pk=None):
        exam = self.get_object()
        student = request.user

        attempt = ExamAttempt.objects.filter(
            student=student,
            exam=exam,
            status='in_progress'
        ).first()

        if not attempt:
            return Response({'success': False, 'message': 'No active attempt found'},
                            status=status.HTTP_404_NOT_FOUND)

        data = request.data
        attempt.current_section_index = data.get('current_section_index', attempt.current_section_index)
        attempt.answers = data.get('answers', attempt.answers)
        attempt.writing_text = data.get('writing_text', attempt.writing_text)
        attempt.flagged = data.get('flagged', attempt.flagged)
        attempt.notepad_text = data.get('notepad_text', attempt.notepad_text)
        attempt.font_level = data.get('font_level', attempt.font_level)
        attempt.section_deadlines = data.get('section_deadlines', attempt.section_deadlines)
        attempt.progress_data = data.get('progress_data', attempt.progress_data)
        attempt.save()

        return Response({'success': True, 'message': 'Progress saved'})

    @action(detail=True, methods=['get'])
    def progress(self, request, pk=None):
        exam = self.get_object()
        student = request.user

        attempt = ExamAttempt.objects.filter(
            student=student,
            exam=exam,
            status='in_progress'
        ).first()

        if not attempt:
            return Response({'success': False, 'message': 'No active attempt found'},
                            status=status.HTTP_404_NOT_FOUND)

        serializer = ExamAttemptSerializer(attempt)
        return Response({'success': True, 'data': serializer.data})

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        exam = self.get_object()
        student = request.user

        attempt = ExamAttempt.objects.filter(
            student=student,
            exam=exam,
            status='in_progress'
        ).first()

        if not attempt:
            return Response({'success': True, 'data': {'attempt_id': None}})

        # Oxirgi holatni ham saqlab qo'yamiz (agar yuborilgan bo'lsa), keyin
        # attempt'ni "submitted" deb belgilaymiz — shu bilan "start" endi
        # shu attempt'ni qaytarmaydi va yangi urinish boshlanadi.
        data = request.data or {}
        if data:
            attempt.current_section_index = data.get('current_section_index', attempt.current_section_index)
            attempt.answers = data.get('answers', attempt.answers)
            attempt.writing_text = data.get('writing_text', attempt.writing_text)
            attempt.flagged = data.get('flagged', attempt.flagged)
            attempt.notepad_text = data.get('notepad_text', attempt.notepad_text)
            attempt.font_level = data.get('font_level', attempt.font_level)
            attempt.section_deadlines = data.get('section_deadlines', attempt.section_deadlines)
            attempt.progress_data = data.get('progress_data', attempt.progress_data)

        attempt.status = 'submitted'
        attempt.submitted_at = timezone.now()
        attempt.save()

        return Response({'success': True, 'data': {'attempt_id': attempt.id}})