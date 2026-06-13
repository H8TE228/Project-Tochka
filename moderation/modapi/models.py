import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class User(AbstractUser):
    pass


class Favorite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product_id = models.UUIDField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "product_id"], name="unique_user_product")
        ]


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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_id = models.UUIDField(unique=True)
    seller_id = models.UUIDField()
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
    class FieldName(models.TextChoices):
        TITLE = 'title', 'Название'
        DESCRIPTION = 'description', 'Описание'
        PRODUCT_IMAGES = 'product_images', 'Изображения товара'
        CATEGORY = 'category', 'Категория'
        SKU_NAME = 'sku_name', 'Название SKU'
        SKU_IMAGE = 'sku_image', 'Изображение SKU'
        SKU_PRICE = 'sku_price', 'Цена SKU'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_moderation = models.ForeignKey(
        ProductModeration, 
        on_delete=models.CASCADE, 
        related_name='field_reports',
        verbose_name="Запись модерации"
    )
    field_name = models.CharField(max_length=14, choices=FieldName)
    sku_id = models.UUIDField(null=True, blank=True)
    comment = models.TextField()
    date_created = models.DateTimeField(auto_now_add=True)