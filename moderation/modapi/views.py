from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from django.forms.fields import BooleanField
from django.core.exceptions import ValidationError as DjangoValidationError

from moderation.authentication import JWTAuthentication, RequireServiceKeyAuthentication
from moderation.permissions import IsServiceAuthenticated

from .serializers import B2BEventSerializer

from .services import (
    MAX_LIMIT,
    DEFAULT_LIMIT,
    UpstreamUnavailable,
    check_idempotency,
    handle_event_created,
    handle_event_edited,
    handle_event_deleted,
)

import uuid
from django.db import models
from django.utils import timezone

from django.db import transaction

from .models import ProductBlockingReason, ProductModeration


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"service": "moderation", "status": "ok"})
    

class B2BEventView(APIView):
    authentication_classes = [RequireServiceKeyAuthentication]
    permission_classes = [IsServiceAuthenticated]

    def post(self, request):
        service_id = request.headers.get("X-Service-Id")
        if not service_id:
            return Response(
                {"code": "INVALID_REQUEST", "message": "Missing X-Service-Id"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        
        serializer = B2BEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        idempotency_key = validated_data.get("idempotency_key")
        if check_idempotency(idempotency_key):
            return Response(status=status.HTTP_202_ACCEPTED)
        
        event_type = validated_data.get('event_type')

        if event_type == "PRODUCT_CREATED":
            return handle_event_created(validated_data=validated_data)
        elif event_type == "PRODUCT_EDITED":
            return handle_event_edited(validated_data=validated_data)
        elif event_type == "PRODUCT_DELETED":
            return handle_event_deleted(validated_data=validated_data)
        
        return Response(status=status.HTTP_400_BAD_REQUEST)