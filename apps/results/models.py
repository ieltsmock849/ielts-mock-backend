from django.db import models
from apps.accounts.models import User, Organization
from apps.exams.models import Exam, ExamAttempt


class ExamResult(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    attempt = models.OneToOneField(ExamAttempt, on_delete=models.CASCADE, null=True, blank=True)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_results')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='results')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)

    overall_band = models.FloatField(null=True, blank=True)
    section_scores = models.JSONField(default=dict)
    section_bands = models.JSONField(default=dict)
    section_raw = models.JSONField(default=dict)
    review_data = models.JSONField(default=dict)
    stats = models.JSONField(default=dict)

    # PERFORMANCE: 'pending_review' holatidagi yozuvlarni topish (CEO/Admin
    # "tekshirilmagan Writing"lar ro'yxati/dashboard) tez-tez filtrlanadi —
    # index qo'shildi (migratsiya: 0002_add_performance_indexes).
    writing_status = models.CharField(max_length=20, default='pending_review', db_index=True)
    writing_band = models.FloatField(null=True, blank=True)
    task1_band = models.FloatField(null=True, blank=True)
    task2_band = models.FloatField(null=True, blank=True)
    task1_criteria = models.JSONField(default=dict)
    task2_criteria = models.JSONField(default=dict)

    exam_title = models.CharField(max_length=200, blank=True)
    exam_type = models.CharField(max_length=20, default='academic')
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'exam_results'