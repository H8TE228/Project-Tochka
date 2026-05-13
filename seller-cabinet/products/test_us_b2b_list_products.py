"""GET /api/v1/products — seller-cabinet: список своих товаров (канон-flow list-products)."""

import uuid

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def test_list_returns_only_own_products(api_client, product_factory, another_seller):
    mine = product_factory(status=Product.Status.MODERATED, title="Mine")
    product_factory(status=Product.Status.MODERATED, title="Theirs", owner=another_seller)

    resp = api_client.get("/api/v1/products")

    assert resp.status_code == 200
    ids = {p["id"] for p in resp.data["items"]}
    assert str(mine.id) in ids
    assert len([p for p in resp.data["items"] if p["title"] == "Theirs"]) == 0


def test_idor_query_param_seller_id_ignored(api_client, product_factory, another_seller):
    mine = product_factory(status=Product.Status.MODERATED, title="Mine")
    theirs = product_factory(status=Product.Status.MODERATED, title="Theirs", owner=another_seller)

    resp = api_client.get(
        f"/api/v1/products?seller_id={another_seller.id}&seller_id={uuid.uuid4()}"
    )

    assert resp.status_code == 200
    ids = {p["id"] for p in resp.data["items"]}
    assert str(mine.id) in ids
    assert str(theirs.id) not in ids


def test_status_filter_deleted_only(api_client, product_factory):
    active = product_factory(status=Product.Status.MODERATED, title="Active", deleted=False)
    deleted = product_factory(status=Product.Status.MODERATED, title="Gone", deleted=True)

    resp = api_client.get("/api/v1/products?status=DELETED")

    assert resp.status_code == 200
    ids = {p["id"] for p in resp.data["items"]}
    assert str(deleted.id) in ids
    assert str(active.id) not in ids


def test_status_filter_blocked_only(api_client, product_factory):
    blocked = product_factory(status=Product.Status.BLOCKED, title="B")
    hard = product_factory(status=Product.Status.HARD_BLOCKED, title="H")
    moderated = product_factory(status=Product.Status.MODERATED, title="M")

    resp = api_client.get("/api/v1/products?status=BLOCKED")

    assert resp.status_code == 200
    ids = {p["id"] for p in resp.data["items"]}
    assert str(blocked.id) in ids
    assert str(hard.id) in ids
    assert str(moderated.id) not in ids


def test_search_by_title_case_insensitive(api_client, product_factory):
    product_factory(title="Телефон")
    product_factory(title="телевизор")
    product_factory(title="Ноутбук")

    resp = api_client.get("/api/v1/products?search=Тел")

    assert resp.status_code == 200
    titles = {p["title"] for p in resp.data["items"]}
    assert titles == {"Телефон", "телевизор"}


def test_skus_count_and_total_active_quantity(api_client, product_factory, sku_factory):
    p = product_factory(status=Product.Status.MODERATED)
    sku_factory(p, active_quantity=10)
    sku_factory(p, active_quantity=40)

    resp = api_client.get("/api/v1/products")

    assert resp.status_code == 200
    row = next(x for x in resp.data["items"] if x["id"] == str(p.id))
    assert row["skus_count"] == 2
    assert row["total_active_quantity"] == 50


def test_pagination_meta(api_client, product_factory):
    for i in range(25):
        product_factory(title=f"P{i}", status=Product.Status.MODERATED)

    r1 = api_client.get("/api/v1/products?limit=20&offset=0")
    assert r1.status_code == 200
    assert r1.data["total"] == 25
    assert r1.data["limit"] == 20
    assert r1.data["offset"] == 0
    assert len(r1.data["items"]) == 20

    r2 = api_client.get("/api/v1/products?limit=20&offset=20")
    assert len(r2.data["items"]) == 5


def test_limit_clamped_to_max_100(api_client, product_factory):
    product_factory(status=Product.Status.MODERATED)
    resp = api_client.get("/api/v1/products?limit=500")
    assert resp.status_code == 200
    assert resp.data["limit"] == 100


def test_invalid_status_returns_400(api_client):
    resp = api_client.get("/api/v1/products?status=UNKNOWN")
    assert resp.status_code == 400
    assert resp.data["code"] == "INVALID_REQUEST"
