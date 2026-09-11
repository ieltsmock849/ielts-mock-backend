from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from apps.results.models import ExamResult
from apps.accounts.models import SupportTicket
from .telegram import send_writing_notification, send_support_ticket_notification
from .realtime import push_to_support


@receiver(post_save, sender=ExamResult)
def notify_writing_submission(sender, instance, created, **kwargs):
    """Send notification when a writing result is created"""
    if not created or instance.writing_status != 'pending_review':
        return

    try:
        student = instance.student
        exam = instance.exam
        org = student.organization

        if org and org.telegram_chat_id:
            send_writing_notification(org, student, exam, instance)
    except Exception as e:
        # Don't fail the request if notification fails
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Writing notification failed: {e}")


@receiver(post_save, sender=SupportTicket)
def notify_support_ticket(sender, instance, created, **kwargs):
    """Send notification when a support ticket is created"""
    if not created:
        return

    try:
        from apps.accounts.models import User
        support_user = User.objects.filter(role='support').first()
        if support_user and support_user.telegram_chat_id:
            send_support_ticket_notification(instance, support_user.telegram_chat_id)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Support ticket notification failed: {e}")

    try:
        # Lazy import — aylanma import (apps.accounts.serializers <-> bu fayl)
        # bo'lmasligi uchun signal ishga tushganda import qilinadi.
        from apps.accounts.serializers import SupportTicketSerializer
        push_to_support('new_support_ticket', SupportTicketSerializer(instance).data)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Support ticket realtime push failed: {e}")