from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["role"] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        user = self.user
        data["user"] = {
            "id": user.id,
            "email": user.email,
            "role": user.role,
        }

        return data


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "role",
            "first_name",
            "last_name",
            "phone_number",
            "profile_picture",
            "country",
            "region",
            "city",
            "district",
            "street",
            "building",
            "apartment",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "role")

    def update(self, instance, validated_data):
        if "profile_picture" in validated_data:
            if instance.profile_picture:
                instance.profile_picture.delete(save=False)
        return super().update(instance, validated_data)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = (
            "email",
            "username",
            "password",
            "password2",
            "phone_number",
            "first_name",
            "last_name",
        )

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({
                "password": "Password fields don't match."
            })
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")

        if not validated_data.get("username"):
            validated_data["username"] = validated_data["email"].split("@")[0]

        user = User.objects.create_user(**validated_data)
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True, validators=[validate_password]
    )

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is not correct")
        return value

    def update(self, instance, validated_data):
        instance.set_password(validated_data["new_password"])
        instance.save()
        return instance


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="Refresh JWT token for adding to blacklist")