from rest_framework import serializers
from .models import Favorite


class FavoritesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Favorite
        fields = ['id', 'user_id', 'product_id', 'added_at',]
        read_only_fields = ['id', 'user_id', 'added_at',]