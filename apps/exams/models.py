from django.db import models
from apps.accounts.models import Organization, User


class Group(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    level = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'groups'


class Exam(models.Model):
    EXAM_TYPES = (
        ('academic', 'Academic'),
        ('general', 'General Training'),
    )
    STATUS_CHOICES = (
        ('on', 'Active'),
        ('off', 'Inactive'),
    )

    id = models.CharField(max_length=50, primary_key=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPES, default='academic')
    # PERFORMANCE: status='on' har bir Student dashboard/login so'rovida
    # filtrlanadi (ExamViewSet.get_queryset) — index qo'shildi (migratsiya:
    # 0002_add_performance_indexes).
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='on', db_index=True)
    assigned_groups = models.ManyToManyField(Group)
    sections_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    reopened_at = models.DateTimeField(null=True, blank=True)
    notif_seen_by = models.ManyToManyField(User, blank=True, related_name='exam_notifications')

    class Meta:
        db_table = 'exams'


class Assignment(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    file_url = models.TextField(blank=True)
    file_name = models.CharField(max_length=200, blank=True)
    file_mime = models.CharField(max_length=100, blank=True)
    groups = models.ManyToManyField(Group)
    target_students = models.ManyToManyField(User, blank=True, related_name='targeted_assignments')
    viewed_by = models.ManyToManyField(User, blank=True, related_name='viewed_assignments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'assignments'


class ExamAttempt(models.Model):
    STATUS_CHOICES = (
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('expired', 'Expired'),
    )

    id = models.CharField(max_length=50, primary_key=True)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_attempts')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    current_section_index = models.IntegerField(default=0)
    answers = models.JSONField(default=dict)
    writing_text = models.JSONField(default=dict)
    flagged = models.JSONField(default=dict)
    notepad_text = models.TextField(blank=True)
    font_level = models.IntegerField(default=1)
    section_deadlines = models.JSONField(default=dict)
    progress_data = models.JSONField(default=dict)

    class Meta:
        db_table = 'exam_attempts'