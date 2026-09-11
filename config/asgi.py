import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# MUHIM: get_asgi_application() Django app registry'ni to'ldiradi — shu
# sabab WebSocket routing'ni import qilishdan OLDIN chaqirilishi shart,
# aks holda "Apps aren't loaded yet" xatosi chiqadi (routing.py ichida
# apps.notifications.consumers -> apps.accounts.models kabi modellar
# import qilinadi).
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from apps.notifications.middleware import JWTAuthMiddlewareStack  # noqa: E402
from apps.notifications.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    # Oddiy HTTP so'rovlar — mavjud Django/DRF app'ining o'ziga (o'zgarishsiz).
    "http": django_asgi_app,

    # WebSocket ulanishlar — real-time xabar/vazifa/mock exam/notification
    # bildirishnomalari uchun. DIQQAT: channels.security.websocket.
    # AllowedHostsOriginValidator ATAYLAB ishlatilmadi — u faqat SAME-ORIGIN
    # (backend domenining o'zi) so'rovlarga ruxsat beradi, lekin bu loyihada
    # frontend butunlay boshqa domenda joylashgan (xuddi HTTP API kabi —
    # CORS_ALLOWED_ORIGINS'ga q.), shu sabab origin tekshiruvi WS handshake'ni
    # noto'g'ri rad etardi. Xavfsizlik — xuddi qolgan API kabi — JWT token
    # orqali (pastga q.: JWTAuthMiddlewareStack), origin orqali emas.
    "websocket": JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
