import os
import logging
import threading
from django.conf import settings

logger = logging.getLogger(__name__)


def escape_telegram_html(text):
    """Escape text for Telegram HTML format"""
    if not text:
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def split_for_telegram(text, limit=3500):
    """Split long text for Telegram message limit"""
    parts = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind('\n', 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        parts.append(remaining)
    return parts


def _send_telegram_message_sync(chat_id, text):
    """Haqiqiy (bloklovchi) Telegram API chaqiruvi — endi faqat fon
    thread'ida ishga tushiriladi (pastga q.: send_telegram_message),
    shuning uchun Telegram tarmog'i sekinlashsa ham asosiy so'rov
    thread'i band bo'lib qolmaydi."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or not chat_id:
        return

    try:
        import requests
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        for chunk in split_for_telegram(text):
            response = requests.post(url, json={
                'chat_id': chat_id,
                'text': chunk,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }, timeout=10)
            if not response.ok:
                logger.error(f"Telegram send error: {response.text}")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


def send_telegram_message(chat_id, text):
    """Telegram xabarini FON THREAD'IDA yuboradi — bu funksiya HTTP
    so'rov/signal ichida chaqirilgani uchun (masalan Writing topshirilganda
    yoki Support ticket yaratilganda), agar shu yerda to'g'ridan-to'g'ri
    (sinxron) requests.post chaqirilsa va Telegram tarmog'i sekin/ishlamay
    qolsa — butun worker bir necha soniyaga band bo'lib qolar, natijada
    O'SHA PAYTDA kelgan boshqa (aloqasiz) so'rovlar ham 502/timeout bilan
    tugar edi. Fon thread'i buni butunlay oldini oladi — asosiy so'rov
    darhol davom etadi, Telegram yuborilishi orqa fonda tugaydi."""
    threading.Thread(
        target=_send_telegram_message_sync,
        args=(chat_id, text),
        daemon=True,
    ).start()


def send_writing_notification(org, student, exam, result):
    """Send writing submission notification to CEO"""
    if not org or not org.telegram_chat_id:
        return

    writing = exam.sections_data.get('writing', {})
    task1 = writing.get('task1', {})
    task2 = writing.get('task2', {})

    wt = result.writing_text if isinstance(result.writing_text, dict) else {'task1': '',
                                                                            'task2': result.writing_text or ''}

    count_words = lambda t: len(str(t).strip().split()) if t else 0

    header = (
        f"✍️ <b>Yangi Writing ishi</b>\n"
        f"👤 O'quvchi: <b>{escape_telegram_html(student.name)}</b>\n"
        f"📝 Mock exam: <b>{escape_telegram_html(exam.title)}</b>\n"
        f"🕒 Topshirildi: {result.submitted_at.strftime('%d %b %Y')}"
    )

    task1_msg = (
        f"<b>📄 Task 1</b>  ({count_words(wt.get('task1'))} / {task1.get('minWords', 150)} so'z)\n\n"
        f"{escape_telegram_html(wt.get('task1', '— yozilmagan —'))}"
    )

    task2_msg = (
        f"<b>📄 Task 2</b>  ({count_words(wt.get('task2'))} / {task2.get('minWords', 250)} so'z)\n\n"
        f"{escape_telegram_html(wt.get('task2', '— yozilmagan —'))}"
    )

    full_msg = f"{header}\n\n{'─' * 20}\n\n{task1_msg}\n\n{'─' * 20}\n\n{task2_msg}"

    send_telegram_message(org.telegram_chat_id, full_msg)


def send_support_ticket_notification(ticket, support_chat_id):
    """Send support ticket notification to support team"""
    if not support_chat_id:
        return

    text = (
        f"🆘 <b>Yangi texnik murojaat</b>\n"
        f"👤 Foydalanuvchi: <b>{escape_telegram_html(ticket.user_name)}</b> ({escape_telegram_html(ticket.user_role)})\n"
        f"{f'🏢 Tashkilot: {escape_telegram_html(ticket.org_name)}' if ticket.org_name else ''}\n"
        f"🕒 Vaqt: {ticket.created_at.strftime('%d %b %Y %H:%M')}\n\n"
        f"📝 Muammo:\n{escape_telegram_html(ticket.message)}"
    )

    send_telegram_message(support_chat_id, text)