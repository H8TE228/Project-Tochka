import uuid

import pytest
from rest_framework.test import APIClient
from django.conf import settings

from products.models import Category, Product, SKU, Seller
from seller_cabinet.authentication import TokenUser


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        auth_user_id=uuid.uuid4(),
        name="Test Seller",
    )


@pytest.fixture
def another_seller(db):
    return Seller.objects.create(
        auth_user_id=uuid.uuid4(),
        name="Another Seller",
    )


@pytest.fixture
def category(db):
    return Category.objects.create(name="Smartphones", slug="smartphones")


@pytest.fixture
def token_user(seller):
    """JWT-user с тем же auth_user_id, что и Seller — get_or_create_seller подхватит."""
    user = TokenUser.__new__(TokenUser)
    user.id = seller.auth_user_id
    user.email = "seller@test.local"
    user.role = "seller"
    return user


@pytest.fixture
def api_client(token_user):
    client = APIClient()
    client.force_authenticate(user=token_user)
    return client


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
def product_factory(seller, category):
    counter = {"i": 0}

    def make(status=Product.Status.CREATED, owner=None, **kwargs):
        counter["i"] += 1
        return Product.objects.create(
            seller=owner or seller,
            category=kwargs.pop("category", category),
            slug=kwargs.pop("slug", f"product-{counter['i']}-{uuid.uuid4().hex[:6]}"),
            title=kwargs.pop("title", f"Product {counter['i']}"),
            description=kwargs.pop("description", "Description"),
            status=status,
            **kwargs,
        )
    return make


@pytest.fixture
def sku_factory():
    counter = {"i": 0}

    def make(product, **kwargs):
        counter["i"] += 1
        return SKU.objects.create(
            product=product,
            name=kwargs.pop("name", f"SKU-{counter['i']}"),
            price=kwargs.pop("price", 100000),
            cost_price=kwargs.pop("cost_price", 50000),
            discount=kwargs.pop("discount", 0),
            image=kwargs.pop("image", "/s3/default.jpg"),
            active_quantity=kwargs.pop("active_quantity", 10),
            reserved_quantity=kwargs.pop("reserved_quantity", 0),
            **kwargs,
        )
    return make