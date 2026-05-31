import uuid

from django.db import models


class Seller(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # seller_id from auth service — stored as UUID reference (no real FK)
    auth_user_id = models.UUIDField(unique=True)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class BlockingReason(models.Model):
    """Справочник причин блокировки. Заполняется Moderation, читается B2B."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500)

    def __str__(self):
        return self.title


class Product(models.Model):
    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        ON_MODERATION = "ON_MODERATION", "On Moderation"
        MODERATED = "MODERATED", "Moderated"
        BLOCKED = "BLOCKED", "Blocked"
        HARD_BLOCKED = "HARD_BLOCKED", "Hard Blocked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name="products")
    slug = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CREATED
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    deleted = models.BooleanField(default=False)

    # Заполняется Moderation при отклонении (B2B-9 и US-B2B-05)
    blocking_reason = models.ForeignKey(
        BlockingReason, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="products",
    )
    moderator_comment = models.TextField(blank=True, default="")
    field_reports = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def blocked(self) -> bool:
        """Производное поле для response — отдельно от status (по канон-flow B2B-5)."""
        return self.status in (self.Status.BLOCKED, self.Status.HARD_BLOCKED)

    def __str__(self):
        return self.title


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    url = models.CharField(max_length=2000)
    ordering = models.IntegerField(default=0)

    class Meta:
        ordering = ["ordering"]

    def __str__(self):
        return self.url


class ProductCharacteristic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="characteristics"
    )
    name = models.CharField(max_length=200)
    value = models.CharField(max_length=2000)

    def __str__(self):
        return f"{self.name}: {self.value}"


class SKU(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="skus"
    )
    name = models.CharField(max_length=500)

    # Все суммы — копейки (integer), как в канон-flow B2B-2
    price = models.IntegerField()              # было price_cents
    cost_price = models.IntegerField(default=0)  # было cost_price_cents
    discount = models.IntegerField(default=0)    # абсолютная скидка в копейках

    # Одно фото на SKU — по канон-flow B2B-2
    image = models.CharField(max_length=2000, default="")

    active_quantity = models.IntegerField(default=0)
    reserved_quantity = models.IntegerField(default=0)
    is_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.title} — {self.name}"


class SKUImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name="images")
    url = models.CharField(max_length=2000)
    ordering = models.IntegerField(default=0)

    class Meta:
        ordering = ["ordering"]

    def __str__(self):
        return self.url


class SKUCharacteristic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.ForeignKey(
        SKU, on_delete=models.CASCADE, related_name="characteristics"
    )
    name = models.CharField(max_length=200)
    value = models.CharField(max_length=2000)

    def __str__(self):
        return f"{self.name}: {self.value}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED", "Partially Accepted"
        ACCEPTED = "ACCEPTED", "Accepted"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name="invoices")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CREATED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return str(self.id)


class InvoiceLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT, related_name="invoice_lines")
    quantity = models.IntegerField()
    accepted_quantity = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.invoice} — {self.sku} x{self.quantity}"


class InventoryReservation(models.Model):
    """Резерв по паре (order_id, sku); количество и время для unreserve и идемпотентности."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.UUIDField(db_index=True)
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name="inventory_reservations")
    quantity = models.IntegerField()
    reserved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order_id", "sku"],
                name="uniq_inventory_reservation_order_sku",
            ),
        ]


class ProcessedRequest(models.Model):
    """Idempotency журнал сервисных команд reserve/unreserve/fulfill."""

    class Action(models.TextChoices):
        RESERVE = "RESERVE", "Reserve"
        UNRESERVE = "UNRESERVE", "Unreserve"
        FULFILL = "FULFILL", "Fulfill"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=20, choices=Action.choices)
    idempotency_key = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["action", "idempotency_key"],
                name="uniq_processed_request_action_idempotency",
            ),
        ]


class ProcessedModerationEvent(models.Model):
    """Idempotency журнал примененных moderation-решений per SKU."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.ForeignKey(
        SKU, on_delete=models.CASCADE, related_name="processed_moderation_events"
    )
    idempotency_key = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sku", "idempotency_key"],
                name="uniq_processed_moderation_event_sku_idempotency",
            ),
        ]
