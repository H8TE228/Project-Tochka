from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError

from django.forms.fields import BooleanField
from django.core.exceptions import ValidationError as DjangoValidationError

from moderation.authentication import JWTAuthentication, RequireServiceKeyAuthentication
from moderation.permissions import IsServiceAuthenticated

from .serializers import (
    B2BEventSerializer,
    QueueClaimRequestSerializer,
    ProductModerationResponseSerializer,
    SoftBlockRequestSerializer,
)

from .services import (
    MAX_LIMIT,
    DEFAULT_LIMIT,
    UpstreamUnavailable,
    check_idempotency,
    handle_event_created,
    handle_event_edited,
    handle_event_deleted,
    publish_moderation_declined_to_b2b,
)

import uuid
from django.db import models, transaction
from django.utils import timezone

from django.db import transaction

from .models import ProductBlockingReason, ProductModeration, ProductModerationFieldReport


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


class QueueClaimView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = QueueClaimRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        queue_id = validated_data.get('queue_priority')
        moderator_id = request.user.id

        if ProductModeration.objects.filter(moderator_id=moderator_id, status='IN_REVIEW').exists():
            return Response(
                {
                    "code": "ALREADY_IN_REVIEW",
                    "message": "You already have a pending product in review.",
                },
                status=status.HTTP_409_CONFLICT
            )
        
        with transaction.atomic():
            queryset = ProductModeration.objects.filter(status='PENDING')

            if queue_id is not None:
                queryset = queryset.filter(queue_priority=queue_id).order_by('date_updated')
            else:
                queryset = queryset.order_by('queue_priority', 'date_updated')

            product_to_review = queryset.select_for_update(skip_locked=True).first()
            if not product_to_review:
                return Response(
                    {"detail": "No pending products available."},
                    status=status.HTTP_204_NO_CONTENT
                )
            
            product_to_review.status = ProductModeration.Status.IN_REVIEW
            product_to_review.moderator_id = moderator_id
            product_to_review.date_updated = timezone.now()
            product_to_review.save()

        serializer = ProductModerationResponseSerializer(product_to_review)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TicketBlockView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_id):
        serializer = SoftBlockRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        blocking_reason = ProductBlockingReason.objects.filter(
            id=data["blocking_reason_id"]
        ).first()
        if blocking_reason is None:
            raise ValidationError({"blocking_reason_id": "Unknown blocking reason."})
        if blocking_reason.hard_block:
            raise ValidationError({
                "blocking_reason_id": "Hard-only reason cannot be used for soft block."
            })

        moderator_id = request.user.id
        with transaction.atomic():
            product = ProductModeration.objects.select_for_update().filter(
                id=ticket_id
            ).first()
            if product is None:
                return Response(
                    {"code": "NOT_FOUND", "message": "Ticket not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if str(product.moderator_id) != str(moderator_id):
                raise PermissionDenied("Cannot decline another moderator's ticket.")
            if product.status != ProductModeration.Status.IN_REVIEW:
                return Response(
                    {"code": "WRONG_STATUS", "message": "Ticket must be in review."},
                    status=status.HTTP_409_CONFLICT,
                )

            reports_data = data["field_reports"]
            ProductModerationFieldReport.objects.filter(
                product_moderation=product
            ).delete()
            ProductModerationFieldReport.objects.bulk_create([
                ProductModerationFieldReport(
                    product_moderation=product,
                    field_name=report["field_name"],
                    sku_id=report.get("sku_id"),
                    comment=report["comment"],
                )
                for report in reports_data
            ])

            product.status = ProductModeration.Status.BLOCKED
            product.blocking_reason = blocking_reason
            product.moderator_comment = data["moderator_comment"]
            product.date_moderation = timezone.now()
            product.date_updated = timezone.now()
            product.save(
                update_fields=[
                    "status",
                    "blocking_reason",
                    "moderator_comment",
                    "date_moderation",
                    "date_updated",
                ]
            )

            publish_moderation_declined_to_b2b(
                product_id=product.product_id,
                blocking_reason_id=blocking_reason.id,
                field_reports=reports_data,
            )

        response_serializer = ProductModerationResponseSerializer(product)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
