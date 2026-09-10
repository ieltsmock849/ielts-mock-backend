from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import SupportTicket
from .serializers import SupportTicketSerializer
from .permissions import IsSupport

class SupportTicketViewSet(viewsets.ModelViewSet):
    serializer_class = SupportTicketSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['seen', 'user_role']
    search_fields = ['message', 'user_name']

    def get_queryset(self):
        user = self.request.user
        if user.role == 'support':
            return SupportTicket.objects.all()
        if user.role == 'ceo':
            # CEO uchun `user` aslida Organization obyekti bo'lgani sabab
            # SupportTicket.user (User FK) bilan solishtirib bo'lmaydi —
            # perform_create'da CEO ticketlari user=None, organization=org
            # qilib saqlanadi, shu sabab shu yerda ham shunga mos filtrlaymiz.
            return SupportTicket.objects.filter(organization=user, user__isnull=True)
        return SupportTicket.objects.filter(user=user)

    def perform_create(self, serializer):
        # CEO login qilganda `user` aslida Organization obyekti bo'ladi va uning
        # 'organization'/'name' maydonlari User modelidagidan farq qiladi —
        # shu sabab CEO uchun alohida holat qaraymiz (aks holda AttributeError
        # yoki noto'g'ri org_name chiqishi mumkin edi).
        user = self.request.user
        if user.role == 'ceo':
            org = user  # Organization obyekti
            display_name = org.ceo_name
        else:
            org = getattr(user, 'organization', None)
            display_name = user.name

        serializer.save(
            user=user if user.role != 'ceo' else None,
            user_name=display_name,
            user_role=user.role,
            organization=org,
            org_name=org.org_name if org else ''
        )

    @action(detail=True, methods=['put'])
    def mark_seen(self, request, pk=None):
        if request.user.role != 'support':
            return Response({'success': False, 'message': 'Permission denied'},
                          status=status.HTTP_403_FORBIDDEN)
        ticket = self.get_object()
        ticket.seen = True
        ticket.save()
        return Response({'success': True, 'message': 'Ticket marked as seen'})