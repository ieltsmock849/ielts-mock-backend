import os
import re
import base64
import shutil
import logging
import tempfile
import threading
import subprocess
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

    # TUZATILDI: ExamResult modelida 'writing_text' degan maydon UMUMAN yo'q
    # (bu doim AttributeError berardi, signals.py'dagi try/except uni jim
    # yutib yuborardi — shu sabab natija muvaffaqiyatli saqlansa ham
    # Telegram xabari hech qachon yuborilmasdi). Haqiqiy writing matni
    # frontend'dan review_data JSON ichida, 'writingText' kaliti ostida
    # keladi (q. frontend index.html: resultToApi -> review_data.writingText).
    wt = result.review_data.get('writingText', {}) if result.review_data else {}
    if not isinstance(wt, dict):
        wt = {'task1': '', 'task2': ''}

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


# ---------------------------------------------------------------------------
# SPEAKING — o'quvchining part-part audio yozuvlarini CEO'ning Telegram
# chatiga yuborish (Writing xabari kabi, ExamResult yaratilganda signal orqali).
# ---------------------------------------------------------------------------

_DATA_URL_RE = re.compile(r'^data:([^;,]+)(?:;[^,]*)?;base64,(.*)$', re.DOTALL)


def _decode_data_url(data_url):
    """'data:audio/webm;base64,....' -> (mime, bytes). Yaroqsiz bo'lsa (None, None)."""
    if not isinstance(data_url, str):
        return None, None
    m = _DATA_URL_RE.match(data_url)
    if not m:
        return None, None
    try:
        return m.group(1).lower(), base64.b64decode(m.group(2))
    except Exception:
        return None, None


def _ffmpeg_exe():
    """Tizimdagi ffmpeg, bo'lmasa imageio-ffmpeg paketi bilan kelgan binary."""
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _webm_to_ogg(raw):
    """Brauzer yozgan webm/opus -> ogg/opus (Telegram ovozli xabari formati).
    Avval qayta kodlamasdan ko'chiriladi (tez, sifat yo'qolmaydi); bo'lmasa
    32k opus'ga qayta kodlanadi. ffmpeg yo'q yoki xato bo'lsa None."""
    exe = _ffmpeg_exe()
    if not exe:
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'in.webm')
            dst = os.path.join(tmp, 'out.ogg')
            with open(src, 'wb') as f:
                f.write(raw)
            for codec_args in (['-c:a', 'copy'], ['-c:a', 'libopus', '-b:a', '32k', '-ar', '48000', '-ac', '1']):
                res = subprocess.run(
                    [exe, '-y', '-loglevel', 'error', '-i', src, '-vn', *codec_args, '-f', 'ogg', dst],
                    capture_output=True, timeout=60,
                )
                if res.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
                    with open(dst, 'rb') as f:
                        return f.read()
    except Exception as e:
        logger.error(f"webm->ogg conversion failed: {e}")
    return None


def _tg_call(method, data, files=None, timeout=60):
    """Telegram Bot API chaqiruvi (bloklovchi — faqat fon thread'ida ishlating)."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return False
    try:
        import requests
        response = requests.post(f"https://api.telegram.org/bot{token}/{method}",
                                 data=data, files=files, timeout=timeout)
        if not response.ok:
            logger.error(f"Telegram {method} error: {response.text}")
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram {method} failed: {e}")
        return False


_MIME_EXT = {
    'audio/webm': 'webm', 'video/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a',
    'audio/x-m4a': 'm4a', 'audio/aac': 'aac', 'audio/mpeg': 'mp3', 'audio/wav': 'wav',
}


def _send_audio_part(chat_id, caption, mime, raw, duration, base_name, performer):
    """Bitta part yozuvini eng qulay formatda yuboradi:
    webm/ogg (opus) -> ovozli xabar (Telegram ichida ijro etiladi),
    mp4/m4a/mp3     -> audio, boshqasi yoki xato bo'lsa -> oddiy fayl (document)."""
    ext = _MIME_EXT.get(mime, 'bin')
    dur = str(int(duration)) if duration else None

    def base(extra=None):
        d = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'}
        if extra:
            d.update(extra)
        return d

    if mime in ('audio/webm', 'video/webm', 'audio/ogg'):
        ogg = raw if mime == 'audio/ogg' else _webm_to_ogg(raw)
        if ogg:
            extra = {'duration': dur} if dur else None
            if _tg_call('sendVoice', base(extra), {'voice': (f'{base_name}.ogg', ogg, 'audio/ogg')}):
                return True
    elif mime in ('audio/mp4', 'audio/x-m4a', 'audio/aac', 'audio/mpeg'):
        extra = {'title': base_name, 'performer': performer}
        if dur:
            extra['duration'] = dur
        if _tg_call('sendAudio', base(extra), {'audio': (f'{base_name}.{ext}', raw, mime)}):
            return True

    # Zaxira variant — original faylni hujjat sifatida yuborish (yuklab olib eshitiladi).
    return _tg_call('sendDocument', base(), {'document': (f'{base_name}.{ext}', raw, mime or 'application/octet-stream')})


def _fmt_duration(sec):
    sec = int(sec or 0)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _build_speaking_caption(part, duration, limit=1000):
    """Part sarlavhasi + savollar (Telegram caption chegarasi 1024 belgi)."""
    lines = [f"🎤 <b>{escape_telegram_html(part.get('title') or 'Speaking')}</b> ({_fmt_duration(duration)})"]
    for i, q in enumerate(part.get('questions') or [], 1):
        text = str((q or {}).get('text', '')).replace('**', '').strip().replace('\n', ' ')
        if len(text) > 300:
            text = text[:300].rstrip() + '…'
        lines.append(f"{i}. {escape_telegram_html(text)}")
    out = ''
    for line in lines:
        if len(out) + len(line) + 1 > limit:
            out += '\n…'
            break
        out += ('\n' if out else '') + line
    return out


def _send_speaking_sync(chat_id, header, items, performer):
    """Fon thread'ida: avval sarlavha xabari, so'ng har bir part yozuvi (tartib saqlanadi)."""
    _send_telegram_message_sync(chat_id, header)
    for item in items:
        try:
            mime, raw = _decode_data_url(item['audioUrl'])
            if not raw:
                _send_telegram_message_sync(chat_id, f"⚠️ {escape_telegram_html(item['title'])}: audioni o'qib bo'lmadi")
                continue
            ok = _send_audio_part(chat_id, item['caption'], mime, raw, item['duration'], item['base_name'], performer)
            if not ok:
                _send_telegram_message_sync(chat_id, f"⚠️ {escape_telegram_html(item['title'])}: audioni yuborib bo'lmadi")
        except Exception as e:
            logger.error(f"Speaking part send failed: {e}")


def send_speaking_notification(org, student, exam, result):
    """Speaking yozuvlarini (part-part) CEO'ga yuboradi — Writing xabari bilan bir xil chatga."""
    if not org or not org.telegram_chat_id or not settings.TELEGRAM_BOT_TOKEN:
        return

    parts = (result.review_data or {}).get('speaking') or []
    parts = [p for p in parts if isinstance(p, dict)]
    if not parts:
        return

    recorded = [p for p in parts if p.get('audioUrl')]
    missing = [p for p in parts if not p.get('audioUrl')]

    header = (
        f"🎤 <b>Yangi Speaking ishi</b>\n"
        f"👤 O'quvchi: <b>{escape_telegram_html(student.name)}</b>\n"
        f"📝 Mock exam: <b>{escape_telegram_html(exam.title)}</b>\n"
        f"🕒 Topshirildi: {result.submitted_at.strftime('%d %b %Y')}\n"
        f"🎙 Yozilgan partlar: {len(recorded)} / {len(parts)}"
    )
    if missing:
        header += "\n⚠️ Yozilmagan: " + ", ".join(escape_telegram_html(p.get('title') or '?') for p in missing)
    if not recorded:
        threading.Thread(target=_send_telegram_message_sync, args=(org.telegram_chat_id, header), daemon=True).start()
        return

    student_slug = re.sub(r'[^A-Za-z0-9]+', '_', str(student.name or 'student')).strip('_') or 'student'
    items = []
    for p in recorded:
        title_slug = re.sub(r'[^A-Za-z0-9]+', '_', str(p.get('title') or 'part')).strip('_') or 'part'
        items.append({
            'title': p.get('title') or 'Speaking',
            'audioUrl': p['audioUrl'],
            'duration': p.get('durationSec') or 0,
            'caption': _build_speaking_caption(p, p.get('durationSec') or 0),
            'base_name': f"{student_slug}_{title_slug}",
        })

    threading.Thread(
        target=_send_speaking_sync,
        args=(org.telegram_chat_id, header, items, str(student.name or '')),
        daemon=True,
    ).start()


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