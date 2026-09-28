# YANGI:
import uuid
from rest_framework import serializers
from .models import ExamResult


class ExamResultSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    exam_title_display = serializers.SerializerMethodField()

    class Meta:
        model = ExamResult
        fields = ['id', 'attempt', 'student', 'student_name', 'exam', 'exam_title_display',
                  'organization', 'overall_band', 'section_scores', 'section_bands',
                  'section_raw', 'review_data', 'stats', 'writing_status', 'writing_band',
                  'task1_band', 'task2_band', 'task1_criteria', 'task2_criteria',
                  'exam_title', 'exam_type', 'submitted_at']
        extra_kwargs = {
            'id': {'required': False},
            'organization': {'required': False},
            'student': {'required': False},
        }

    def get_student_name(self, obj):
        return obj.student.name if obj.student else None

    def get_exam_title_display(self, obj):
        return obj.exam.title if obj.exam else obj.exam_title

    def create(self, validated_data):
        validated_data.setdefault('id', f"res_{uuid.uuid4().hex[:12]}")
        return super().create(validated_data)

    def to_representation(self, instance):
        # PERFORMANCE: Speaking yozuvlari base64 audio sifatida review_data['speaking']
        # ichida saqlanadi (har biri bir necha yuz KB). Ro'yxat/yaratish javoblarida
        # ularni qaytarmaymiz — audio faqat alohida /results/<id>/speaking/
        # endpointi orqali olinadi. Part ma'lumotlari (nom, savollar, davomiylik,
        # 'recorded' bayrog'i) qoladi.
        data = super().to_representation(instance)
        review = data.get('review_data')
        if isinstance(review, dict) and isinstance(review.get('speaking'), list):
            slim = [
                {k: v for k, v in part.items() if k != 'audioUrl'} if isinstance(part, dict) else part
                for part in review['speaking']
            ]
            data['review_data'] = {**review, 'speaking': slim}
        return data


class GradeWritingSerializer(serializers.Serializer):
    task1_criteria = serializers.DictField(required=False)
    task2_criteria = serializers.DictField(required=False)
    task1_band = serializers.FloatField(required=False, allow_null=True)
    task2_band = serializers.FloatField(required=False, allow_null=True)
    band = serializers.FloatField(required=False, allow_null=True)