from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from django.forms.fields import BooleanField
from django.core.exceptions import ValidationError as DjangoValidationError

from moderation.authentication import JWTAuthentication

from .services import (
    MAX_LIMIT,
    DEFAULT_LIMIT,
    UpstreamUnavailable,
)

import uuid
from django.db import models
from django.utils import timezone

from django.db import transaction


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"service": "moderation", "status": "ok"})
    

