from django.urls import path

from .views import B2BEventView, QueueClaimView, TicketApproveView

urlpatterns = [
    path('b2b/events', B2BEventView.as_view(), name='b2b-event'),
    path('queue/claim', QueueClaimView.as_view(), name='queue-claim'),
    path('tickets/<uuid:ticket_id>/approve', TicketApproveView.as_view(), name='ticket-approve'),
]