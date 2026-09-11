"""
WebSocket (ASGI) ulanishlar uchun JWT autentifikatsiya middleware'i.

Bu — apps/accounts/authentication.py'dagi CustomJWTAuthentication'ning
Channels/ASGI versiyasi: xuddi shu qoidalar bilan (role='ceo' bo'lsa
Organization, aks holda User) token'dagi user_id/role claim'lariga qarab
hisobni topadi. Shunda REST API va WebSocket bir xil JWT token va bir xil
foydalanuvchi modeliga tayanadi — ikkita alohida auth tizimi bo'lmaydi.

Brauzer native WebSocket API handshake so'roviga maxsus Authorization
header qo'sha olmaydi, shu sabab access token query-string orqali
yuboriladi:
    wss://backend/ws/notifications/?token=<access_token>
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def _get_account_from_token(token_str):
    from apps.accounts.models import Organization, User

    if not token_str:
        return None

    try:
        token = AccessToken(token_str)
    except TokenError:
        return None

    user_id = token.get('user_id')
    role = token.get('role')
    if user_id is None:
        return None

    if role == 'ceo':
        account = Organization.objects.filter(id=user_id).first()
        if account is not None:
            account.role = 'ceo'
    else:
        account = User.objects.filter(id=user_id).first()

    if account is not None:
        account.is_authenticated = True
    return account


class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query_string = scope.get('query_string', b'').decode()
        token = parse_qs(query_string).get('token', [None])[0]
        scope['user'] = await _get_account_from_token(token)
        return await self.app(scope, receive, send)


def JWTAuthMiddlewareStack(app):
    return JWTAuthMiddleware(app)
