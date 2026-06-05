import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    pass
 

class Favorite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product_id = models.UUIDField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product_id"],
                name="unique_user_product"
            )
        ]