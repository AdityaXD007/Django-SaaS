from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.tenants.models import Membership

from .models import Invitation


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Invitation.Role.choices, default=Invitation.Role.MEMBER)

    def validate_email(self, value: str) -> str:
        return value.lower()


class InvitationListSerializer(serializers.ModelSerializer):
    """Safe serializer — never exposes the raw token or the token_hash."""

    class Meta:
        model = Invitation
        fields = ("id", "email", "role", "invited_by", "created_at", "expires_at")
        read_only_fields = fields


class InvitationCreateResponseSerializer(serializers.ModelSerializer):
    """
    Response serializer for invite creation.
    Includes the raw token ONLY when INVITATION_RETURN_TOKEN is True (dev convenience);
    in production the token is emailed and never returned by the API.
    """

    token = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = ("id", "email", "role", "created_at", "expires_at", "token")
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_token(self, obj) -> str | None:
        # `_raw_token` is a transient attribute set by the view — not stored.
        if getattr(settings, "INVITATION_RETURN_TOKEN", False):
            return getattr(obj, "_raw_token", None)
        return None


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True)


class MembershipRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ("id", "role", "created_at")
        read_only_fields = fields
