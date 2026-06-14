from urllib.parse import urljoin

import uuid

import requests
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache

from rest_framework.exceptions import NotFound, APIException, ValidationError
from rest_framework.response import Response
from rest_framework import status

from .models import ProductModeration, ProductModerationFieldReport


ALLOWED_SORTS = ("price_asc", "price_desc", "popularity", "new")
UPSTREAM_SORTS = {
    "popularity": "popular",
    "new": "created_desc",
}
FILTER_PARAM_ALIASES = {
    "category_id": "category_id",
    "price_min": "min_price",
    "price_max": "max_price",
    "seller_id": "seller_id",
}
PUBLIC_PRODUCT_PARAMS = ("category_id", "sort")
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
B2B_TIMEOUT_SEC = 3
MIN_SEARCH_LENGTH = 3
MAX_SEARCH_LENGTH = 200


class UpstreamUnavailable(Exception):
    pass


class BrokenHierarchyException(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = {
        "error": "orphan_node",
        "message": "category hierarchy is broken"
    }
    default_code = "orphan_node"


class UpstreamException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"}
    default_code = "UPSTREAM_UNAVAILABLE"


def b2b_get(path: str, params: list[tuple[str, str]]):
    url = urljoin(settings.B2B_URL.rstrip("/") + "/", path.lstrip("/"))
    try:
        response = requests.get(
            url,
            params=params,
            headers={"X-Service-Key": settings.SERVICE_API_KEY},
            timeout=B2B_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise UpstreamUnavailable from exc
    return response


def b2b_post(path: str, json_data: dict | None, params: list[tuple[str, str]]):
    url = urljoin(settings.B2B_URL.rstrip("/") + "/", path.lstrip("/"))
    try:
        response = requests.post(
            url,
            params=params,
            json=json_data,
            headers={"X-Service-Key": settings.SERVICE_API_KEY},
            timeout=B2B_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise UpstreamUnavailable from exc
    return response


def check_idempotency(idempotency_key: str) -> bool:
    if not idempotency_key:
        return False
    
    cache_key = f"idempotency:{idempotency_key}"
    ttl = getattr(settings, 'KEY_CACHE_TTL', 86400)
    
    if cache.add(cache_key, True, ttl):
        return False  # Новый ключ, обработка разрешена
    
    return True  # Дубликат


def handle_event_created(validated_data):
    product_id = validated_data.get("payload").get('product_id')
    seller_id = validated_data.get("payload").get('seller_id')

    mod_obj = ProductModeration.objects.filter(product_id=product_id).first()
    if mod_obj and mod_obj.status == ProductModeration.Status.HARD_BLOCKED:
        return Response(status=status.HTTP_202_ACCEPTED)
    if mod_obj:
        return Response(status=status.HTTP_400_BAD_REQUEST)

    try:
        upstream_response = b2b_get(f"/api/v1/products/{product_id}", [])
    except UpstreamUnavailable:
        raise UpstreamException()
    if upstream_response.status_code != status.HTTP_200_OK:
        raise UpstreamException()
    response = upstream_response.json()

    obj = ProductModeration(
        product_id=product_id,
        seller_id=seller_id,
        json_before=None,
        json_after=response,
        status=ProductModeration.Status.PENDING,
        queue_priority=1,
        ticket_kind = ProductModeration.TicketKind.CREATE
    )
    obj.save()
    return Response(status=status.HTTP_202_ACCEPTED)


def handle_event_edited(validated_data):
    product_id = validated_data.get("payload").get('product_id')

    mod_obj = ProductModeration.objects.filter(product_id=product_id).first()
    if not mod_obj:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    if mod_obj.status == ProductModeration.Status.HARD_BLOCKED:
        return Response(status=status.HTTP_202_ACCEPTED)
    
    try:
        upstream_response = b2b_get(f"/api/v1/products/{product_id}", [])
    except UpstreamUnavailable:
        raise UpstreamException()
    if upstream_response.status_code != status.HTTP_200_OK:
        raise UpstreamException()
    response = upstream_response.json()

    with transaction.atomic():
        mod_obj.json_before = mod_obj.json_after
        mod_obj.json_after = response
        mod_obj.status = ProductModeration.Status.PENDING
        mod_obj.moderator_id = None
        mod_obj.ticket_kind = ProductModeration.TicketKind.EDIT
        mod_obj.save()

        ProductModerationFieldReport.objects.filter(product_moderation=mod_obj).delete()

    return Response(status=status.HTTP_202_ACCEPTED)


def handle_event_deleted(validated_data):
    product_id = validated_data.get("payload").get('product_id')
    mod_obj = ProductModeration.objects.filter(product_id=product_id).first()
    if not mod_obj:
        return Response(status=status.HTTP_202_ACCEPTED)
    mod_obj.delete()
    return Response(status=status.HTTP_202_ACCEPTED)


def handle_ticket_approval(request, ticket_id, comment=None):
    product_card = ProductModeration.objects.filter(id=ticket_id).first()
    
    if product_card is None:
        return Response(status=status.HTTP_404_NOT_FOUND)
    if product_card.status == ProductModeration.Status.HARD_BLOCKED:
        return Response(
            {"code": "TICKET_WRONG_STATUS", "message": "Product is permanently blocked"},
            status=status.HTTP_409_CONFLICT
        )
    if product_card.status != ProductModeration.Status.IN_REVIEW:
        return Response(
            {"code": "TICKET_WRONG_STATUS", "message": "Product is not in review"},
            status=status.HTTP_409_CONFLICT
        )
    if str(product_card.moderator_id) != request.user.id:
        return Response(
            {"code": "TICKET_WRONG_MODERATOR", "message": "Not assigned to you"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    product_id = product_card.product_id
    
    try:
        upstream_response = b2b_get(f"/api/v1/products/{product_id}", [])
    except UpstreamUnavailable:
        pass
    if upstream_response and upstream_response.status_code == status.HTTP_200_OK:
        response = upstream_response.json() 
        skus = response.get("skus", [])
        if len(skus) == 0:
            return Response(
                {"code": "TICKET_HAS_NO_SKUS", "message": "Product has no SKUs, cannot approve"},
                status=status.HTTP_409_CONFLICT
            )
    
    with transaction.atomic():
        product_card = ProductModeration.objects.select_for_update().get(id=ticket_id)
        product_card.status = ProductModeration.Status.MODERATED
        product_card.date_moderation = timezone.now()
        if comment is not None:
            product_card.moderator_comment = comment
        product_card.blocking_reason = None
        product_card.save()
        ProductModerationFieldReport.objects.filter(product_moderation=product_id).delete()

    json_body = {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(product_id),
        "event_type": "MODERATED",
        "moderator_id": str(request.user.id),
        "moderator_comment": comment,
        "occurred_at": product_card.date_moderation.isoformat()
    }

    try:
        upstream_response = b2b_post("/api/v1/moderation/events", json_data=json_body, params=[])
    except UpstreamUnavailable:
        ProductModeration.objects.filter(id=ticket_id).update(status=ProductModeration.Status.IN_REVIEW)
        raise UpstreamException()
    if upstream_response.status_code != status.HTTP_204_NO_CONTENT:
        ProductModeration.objects.filter(id=ticket_id).update(status=ProductModeration.Status.IN_REVIEW)
        raise UpstreamException()
    
    response_json = {
        "id": str(ticket_id),
        "product_id": str(product_id),
        "seller_id": str(product_card.seller_id),
        "kind": product_card.ticket_kind,
        "status": "MODERATED",
        "queue_priority": product_card.queue_priority,
        "assigned_moderator_id": str(request.user.id),
        "decision_at": product_card.date_moderation.isoformat(),
        "created_at": product_card.date_created.isoformat(),
        "updated_at": product_card.date_updated.isoformat()
    }
    return Response(response_json, status=status.HTTP_200_OK)