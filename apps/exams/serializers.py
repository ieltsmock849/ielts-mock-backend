import uuid
from rest_framework import serializers
from .models import Group, Exam, Assignment, ExamAttempt
from apps.accounts.models import User, Organization


class GroupSerializer(serializers.ModelSerializer):
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'organization', 'name', 'level', 'student_count', 'created_at']
        extra_kwargs = {
            'id': {'required': False},
            'organization': {'required': False},
        }

    def get_student_count(self, obj):
        # PERFORMANCE: GroupViewSet.get_queryset() endi student_count'ni
        # .annotate() bilan bitta query'da hisoblab beradi — shu bo'lsa
        # o'shani ishlatamiz (guruhlar ro'yxatida har bir guruh uchun
        # alohida COUNT query'siga yo'l qo'ymaslik uchun). Annotatsiya
        # mavjud bo'lmagan holatlarda (masalan create()/update() natijasini
        # to'g'ridan-to'g'ri serializatsiya qilishda) eski usulga qaytamiz —
        # natija bir xil, faqat samaradorlik farq qiladi.
        if hasattr(obj, 'student_count'):
            return obj.student_count
        return User.objects.filter(group=obj, role='student').count()

    def create(self, validated_data):
        validated_data.setdefault('id', f"grp_{uuid.uuid4().hex[:12]}")
        return super().create(validated_data)


class ExamSerializer(serializers.ModelSerializer):
    assigned_group_ids = serializers.SerializerMethodField()
    enabled_sections = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ['id', 'organization', 'title', 'exam_type', 'status', 'assigned_groups',
                  'assigned_group_ids', 'sections_data', 'enabled_sections', 'created_at',
                  'reopened_at', 'notif_seen_by']
        extra_kwargs = {
            'id': {'required': False},
            'organization': {'required': False},
            'assigned_groups': {'required': False},
            'notif_seen_by': {'required': False},
        }

    def get_assigned_group_ids(self, obj):
        # PERFORMANCE: .values_list() manager'da to'g'ridan-to'g'ri chaqirilsa
        # HAR DOIM yangi query yuboradi — hatto ExamViewSet.get_queryset()
        # .prefetch_related('assigned_groups') qilgan bo'lsa ham (chunki
        # .values_list() prefetch keshini emas, yangi QuerySet yaratadi).
        # .all() esa prefetch keshini hurmat qiladi — natija bir xil, lekin
        # exam ro'yxatida N+1 query o'rniga bitta (prefetch) query bo'ladi.
        return [g.id for g in obj.assigned_groups.all()]

    def get_enabled_sections(self, obj):
        sections = obj.sections_data or {}
        return [k for k, v in sections.items() if v.get('enabled')]

    def create(self, validated_data):
        validated_data.setdefault('id', f"exam_{uuid.uuid4().hex[:12]}")
        return super().create(validated_data)


class AssignmentSerializer(serializers.ModelSerializer):
    group_ids = serializers.SerializerMethodField()
    target_student_ids = serializers.SerializerMethodField()
    viewed_by_ids = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = ['id', 'organization', 'title', 'content', 'file_url', 'file_name',
                  'file_mime', 'groups', 'group_ids', 'target_students', 'target_student_ids',
                  'viewed_by', 'viewed_by_ids', 'created_at']
        extra_kwargs = {
            'id': {'required': False},
            'organization': {'required': False},
            'groups': {'required': False},
            'target_students': {'required': False},
            'viewed_by': {'required': False},
        }

    def get_group_ids(self, obj):
        # PERFORMANCE: .all() ishlatiladi (.values_list() emas) — shunda
        # AssignmentViewSet.get_queryset()dagi prefetch_related('groups')
        # keshi hurmat qilinadi va ro'yxatda N+1 query bo'lmaydi.
        return [g.id for g in obj.groups.all()]

    def get_target_student_ids(self, obj):
        return [s.id for s in obj.target_students.all()]

    def get_viewed_by_ids(self, obj):
        return [u.id for u in obj.viewed_by.all()]

    def create(self, validated_data):
        validated_data.setdefault('id', f"asg_{uuid.uuid4().hex[:12]}")
        return super().create(validated_data)


class ExamAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamAttempt
        fields = ['id', 'student', 'exam', 'status', 'started_at', 'submitted_at',
                  'current_section_index', 'answers', 'writing_text', 'flagged',
                  'notepad_text', 'font_level', 'section_deadlines', 'progress_data']