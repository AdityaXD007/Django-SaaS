from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Membership, Tenant

User = get_user_model()


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ("id", "name", "slug", "is_active", "created_at")
        read_only_fields = fields


class TenantWorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="membership.role", read_only=True)

    class Meta:
        model = Tenant
        fields = ("id", "name", "slug", "is_active", "role", "created_at")
        read_only_fields = fields


class MemberUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "full_name")
        read_only_fields = fields


class TenantMemberSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "user", "role", "created_at")
        read_only_fields = fields
