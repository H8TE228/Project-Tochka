from rest_framework import serializers
from .models import ProductModeration, ProductBlockingReason, ProductModerationFieldReport


class EventProductCreatedSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    seller_id = serializers.UUIDField()
    category_id = serializers.UUIDField(required=False)
    queue_priority = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=4,
        default=3
    )
    json_after = serializers.JSONField()


class EventProductEditedSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    seller_id = serializers.UUIDField()
    category_id = serializers.UUIDField(required=False)
    queue_priority = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=4,
        default=3
    )
    json_before = serializers.JSONField()
    json_after = serializers.JSONField()


class EventProductDeletedSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()


class B2BEventSerializer(serializers.Serializer):
    MAPPING = {
        'PRODUCT_CREATED': EventProductCreatedSerializer,
        'PRODUCT_EDITED': EventProductEditedSerializer,
        'PRODUCT_DELETED': EventProductDeletedSerializer,
    }

    event_type = serializers.ChoiceField(choices=list(MAPPING.keys()))
    idempotency_key = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()
    payload = serializers.JSONField()

    def validate(self, data):
        event_type = data.get('event_type')
        payload = data.get('payload')

        serializer_class = self.MAPPING.get(event_type)
        
        if serializer_class:
            if not isinstance(payload, dict):
                payload = {}
                
            sub_serializer = serializer_class(data=payload)
            
            if not sub_serializer.is_valid():
                raise serializers.ValidationError({
                    "payload": sub_serializer.errors
                })
                
            data['payload'] = sub_serializer.validated_data
        
        return data


class QueueClaimRequestSerializer(serializers.Serializer):
    queue_priority = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=4,
    )
    category_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        required=False
    )


class FieldReportRequestSerializer(serializers.Serializer):
    """
    moderation/openapi.yaml:756-770 FieldReport — required: [field_path, message].

    field_path — произвольная строка (JSONPath-подобный путь, например 'images[0].url').
    message — текст, maxLength: 1000.
    """
    field_path = serializers.CharField(max_length=255)
    sku_id = serializers.UUIDField(required=False, allow_null=True)
    message = serializers.CharField(max_length=1000)


class SoftBlockRequestSerializer(serializers.Serializer):
    """
    moderation/openapi.yaml:774 BlockDecisionRequest — required: [blocking_reason_ids].

    Поле — массив UUID. Hard/soft маршрут вычисляется во view:
    если хотя бы одна из причин имеет hard_block=True → HARD_BLOCKED, иначе BLOCKED.
    """
    blocking_reason_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        allow_empty=False,
    )
    moderator_comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=2000,
    )
    field_reports = FieldReportRequestSerializer(many=True, required=False, default=list)


class ProductBlockingReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductBlockingReason
        fields = ['id', 'title', 'hard_block']


class ProductModerationResponseSerializer(serializers.ModelSerializer):
    blocking_reason = ProductBlockingReasonSerializer(read_only=True)
    created_at = serializers.DateTimeField(source='date_created', read_only=True)

    class Meta:
        model = ProductModeration
        fields = [
            'id',
            'product_id',
            'seller_id',
            'kind',
            'status',
            'queue_priority',
            'json_before',
            'json_after',
            'blocking_reason',
            'moderator_id',
            'moderator_comment',
            'created_at',
            'date_updated',
            'date_moderation',
        ]
        read_only_fields = fields
