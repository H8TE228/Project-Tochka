import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class User(AbstractUser):
    pass


class ProductBlockingReason(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    hard_block = models.BooleanField(default=False)


class ProductModeration(models.Model):
    class Status(models.TextChoices):        
        PENDING = 'PENDING', 'PENDING'
        IN_REVIEW = 'IN_REVIEW', 'IN_REVIEW'
        MODERATED = 'MODERATED', 'MODERATED'
        BLOCKED = 'BLOCKED', 'BLOCKED'
        HARD_BLOCKED = 'HARD_BLOCKED', 'HARD_BLOCKED'

    class Kind(models.TextChoices):
        CREATE = 'CREATE', 'CREATE'
        EDIT = 'EDIT', 'EDIT'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_id = models.UUIDField(unique=True)
    seller_id = models.UUIDField()
    kind = models.CharField(max_length=6, choices=Kind, default=Kind.CREATE)
    status = models.CharField(max_length=12, choices=Status)
    queue_priority = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(4)])
    json_before = models.JSONField(null=True, blank=True)
    json_after = models.JSONField()
    blocking_reason = models.ForeignKey(ProductBlockingReason, on_delete=models.SET_NULL, null=True, blank=True)
    moderator_id = models.UUIDField(null=True, blank=True)
    moderator_comment = models.TextField(blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    date_moderation = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(queue_priority__gte=1, queue_priority__lte=4),
                name="queue_priority_range_1_to_4",
            )
        ]


class ProductModerationFieldReport(models.Model):
    """
    moderation/openapi.yaml:756-770 FieldReport — required: [field_path, message].

    field_path — произвольный JSONPath-подобный путь (например 'images[0].url'),
    message — текст до 1000 символов.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_moderation = models.ForeignKey(
        ProductModeration,
        on_delete=models.CASCADE,
        related_name='field_reports',
        verbose_name="Запись модерации"
    )
    field_path = models.CharField(max_length=255)
    sku_id = models.UUIDField(null=True, blank=True)
    message = models.TextField()
    date_created = models.DateTimeField(auto_now_add=True)
