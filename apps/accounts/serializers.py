from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.tenants.models import Membership, Tenant

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "full_name", "date_joined")
        read_only_fields = fields


class TenantSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ("id", "name", "slug")
        read_only_fields = fields


class UserMembershipSerializer(serializers.ModelSerializer):
    tenant = TenantSummarySerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ("tenant", "role", "created_at")
        read_only_fields = fields


class UserProfileSerializer(serializers.ModelSerializer):
    memberships = UserMembershipSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "date_joined", "memberships")
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    full_name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
    tenant_name = serializers.CharField(max_length=255, required=True)

    def validate_email(self, value: str) -> str:
        normalized_email = value.strip().lower()
        if User.objects.filter(email__iexact=normalized_email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized_email

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate_tenant_name(self, value: str) -> str:
        stripped_name = value.strip()
        if not stripped_name:
            raise serializers.ValidationError("Tenant name cannot be blank.")
        return stripped_name
