import uuid

import pytest
from rest_framework.test import APIClient
from django.conf import settings

from modapi.models import ProductModeration, ProductBlockingReason


@pytest.fixture
def service_key(settings):
    settings.SERVICE_API_KEY = "test-service-key"
    return settings.SERVICE_API_KEY


@pytest.fixture
def service_api_client(service_key):
    client = APIClient()
    client.credentials(HTTP_X_SERVICE_KEY=service_key, HTTP_X_SERVICE_ID="test-service")
    return client


@pytest.fixture
def product_moderation_factory(db):
    """Factory для создания ProductModeration объектов."""
    counter = {"i": 0}

    def make(
        status="PENDING",
        product_id=None,
        seller_id=None,
        json_after=None,
        blocking_reason=None,
        **kwargs
    ):
        counter["i"] += 1
        return ProductModeration.objects.create(
            product_id=product_id or uuid.uuid4(),
            seller_id=seller_id or uuid.uuid4(),
            status=status,
            queue_priority=kwargs.pop("queue_priority", 1),
            json_before=kwargs.pop("json_before", None),
            json_after=json_after or {"title": f"Product {counter['i']}"},
            blocking_reason=blocking_reason,
            moderator_id=kwargs.pop("moderator_id", None),
            moderator_comment=kwargs.pop("moderator_comment", ""),
            **kwargs
        )
    return make


@pytest.fixture
def blocking_reason_factory(db):
    """Factory для создания ProductBlockingReason объектов."""
    counter = {"i": 0}

    def make(title=None, hard_block=False, **kwargs):
        counter["i"] += 1
        return ProductBlockingReason.objects.create(
            title=title or f"Blocking Reason {counter['i']}",
            hard_block=hard_block,
            **kwargs
        )
    return make
