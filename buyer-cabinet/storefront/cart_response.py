"""
US-CART-03: сборка CartResponse по контракту b2c/cart OpenAPI.

Обязательные поля корзины: items_count, subtotal, is_valid.
Обязательные поля позиции: unit_price, is_available, line_total, available_quantity.
"""
from .services import b2b_get_products


class _SkuLookup:
    """Утилиты для обогащения корзины из B2B."""

    @staticmethod
    def collect_sku_data(sku_ids: set[str]) -> dict:
        result = {}
        try:
            data = b2b_get_products([("limit", "1000"), ("offset", "0")])
        except Exception:
            return result
        items = data.get("items", []) if isinstance(data, dict) else []
        for product in items:
            for sku in product.get("skus", []) or []:
                if str(sku.get("id")) in sku_ids:
                    result[str(sku["id"])] = {"sku": sku, "product": product}
        return result


def empty_cart_response() -> dict:
    """Пустая корзина — та же форма, что CartResponse."""
    return {
        "id": None,
        "items": [],
        "items_count": 0,
        "subtotal": 0,
        "is_valid": False,
    }


def _item_row(
    *,
    sku_id: str,
    quantity: int,
    is_available: bool,
    unavailable_reason: str | None,
    unit_price: int | None,
    line_total: int | None,
    available_quantity: int,
    name: str | None,
    image: str | None,
    product_id: str | None,
) -> dict:
    return {
        "sku_id": sku_id,
        "quantity": quantity,
        "is_available": is_available,
        "unavailable_reason": unavailable_reason,
        "unit_price": unit_price,
        "line_total": line_total,
        "available_quantity": available_quantity,
        "name": name,
        "image": image,
        "product_id": product_id,
    }


def enrich_cart_items(cart) -> dict:
    """Собирает CartResponse с обогащением из B2B и пометкой недоступных позиций."""
    items_qs = list(cart.items.all())
    sku_ids = {str(i.sku_id) for i in items_qs}
    sku_data = _SkuLookup.collect_sku_data(sku_ids) if sku_ids else {}

    enriched = []
    subtotal = 0
    all_available = True

    for item in items_qs:
        sid = str(item.sku_id)

        if item.unavailable_reason:
            all_available = False
            bundle = sku_data.get(sid)
            unit_price = None
            name = None
            image = None
            product_id = None
            if bundle:
                sku = bundle["sku"]
                product = bundle["product"]
                name = sku.get("name") or product.get("title") or ""
                image = sku.get("image") or ""
                product_id = str(product.get("id")) if product.get("id") else None
                unit_price = int(sku.get("price") or 0)
            enriched.append(_item_row(
                sku_id=sid,
                quantity=item.quantity,
                is_available=False,
                unavailable_reason=item.unavailable_reason,
                unit_price=unit_price,
                line_total=0,
                available_quantity=0,
                name=name,
                image=image,
                product_id=product_id,
            ))
            continue

        bundle = sku_data.get(sid)
        if bundle is None:
            all_available = False
            enriched.append(_item_row(
                sku_id=sid,
                quantity=item.quantity,
                is_available=False,
                unavailable_reason="sku_not_found",
                unit_price=None,
                line_total=None,
                available_quantity=0,
                name=None,
                image=None,
                product_id=None,
            ))
            continue

        sku = bundle["sku"]
        product = bundle["product"]
        available_qty = int(sku.get("active_quantity") or 0)
        unit_price = int(sku.get("price") or 0)
        unavailable_reason = None
        if available_qty <= 0:
            unavailable_reason = "out_of_stock"
        elif available_qty < item.quantity:
            unavailable_reason = "insufficient_stock"
        is_available = unavailable_reason is None
        if not is_available:
            all_available = False

        line_total = unit_price * item.quantity if is_available else 0
        enriched.append(_item_row(
            sku_id=sid,
            quantity=item.quantity,
            is_available=is_available,
            unavailable_reason=unavailable_reason,
            unit_price=unit_price,
            line_total=line_total,
            available_quantity=available_qty,
            name=sku.get("name") or product.get("title") or "",
            image=sku.get("image") or "",
            product_id=str(product.get("id")) if product.get("id") else None,
        ))
        if is_available:
            subtotal += line_total

    items_count = sum(row["quantity"] for row in enriched)
    return {
        "id": str(cart.id),
        "items": enriched,
        "items_count": items_count,
        "subtotal": subtotal,
        "is_valid": all_available and bool(enriched),
    }
