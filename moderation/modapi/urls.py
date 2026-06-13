from django.urls import path

from .views import B2BEventView

urlpatterns = [
    path('b2b/events', B2BEventView.as_view(), name='b2b-event'),
]