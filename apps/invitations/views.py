import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Membership
from apps.tenants.permissions import HasTenantRole

from .models import Invitation
from .serializers import (
    AcceptInvitationSerializer,
    InvitationCreateResponseSerializer,
    InvitationCreateSerializer,
    InvitationListSerializer,
)
from .tasks import send_invitation_email

_ACCEPT_ERROR = "Invalid, expired, or already-used invitation."


def _expiry_days() -> int:
    return int(getattr(settings, "INVITATION_EXPIRY_DAYS", 7))


class TenantInvitationListCreateView(APIView):
    """
    GET  — list pending invitations for the current tenant (admin+).
    POST — create a new invitation (admin+).
    """

    permission_classes = (IsAuthenticated, HasTenantRole("admin"))

    @extend_schema(
        summary="List pending invitations",
        responses={200: InvitationListSerializer(many=True)},
    )
    def get(self, request):
        invitations = Invitation.objects.filter(
            tenant=request.tenant,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        ).order_by("-created_at")
        return Response(InvitationListSerializer(invitations, many=True).data)

    @extend_schema(
        summary="Create an invitation",
        request=InvitationCreateSerializer,
        responses={201: InvitationCreateResponseSerializer},
    )
    def post(self, request):
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        role = serializer.validated_data["role"]

        # Reject if email is already a tenant member.
        if Membership.objects.filter(tenant=request.tenant, user__email=email).exists():
            raise ValidationError(
                {"email": "This email address is already a member of the tenant."}
            )

        raw_token = secrets.token_urlsafe(32)
        token_hash = Invitation.hash_token(raw_token)

        try:
            with transaction.atomic():
                invitation = Invitation.objects.create(
                    tenant=request.tenant,
                    email=email,
                    role=role,
                    token_hash=token_hash,
                    invited_by=request.user,
                    expires_at=timezone.now() + timedelta(days=_expiry_days()),
                )
                # Dispatch email task only after the DB transaction commits.
                transaction.on_commit(
                    lambda: send_invitation_email.delay(str(invitation.id), raw_token)
                )
        except IntegrityError as exc:
            raise ValidationError(
                {"email": "A pending invitation for this email already exists in this tenant."}
            ) from exc

        # Attach the raw token transiently for the response serializer.
        invitation._raw_token = raw_token

        response_serializer = InvitationCreateResponseSerializer(invitation)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class TenantInvitationRevokeView(APIView):
    """DELETE — revoke an invitation (admin+)."""

    permission_classes = (IsAuthenticated, HasTenantRole("admin"))

    @extend_schema(
        summary="Revoke an invitation",
        responses={204: None},
    )
    def delete(self, request, invitation_id):
        try:
            invitation = Invitation.objects.get(
                id=invitation_id,
                tenant=request.tenant,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            )
        except Invitation.DoesNotExist as exc:
            raise NotFound() from exc

        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AcceptInvitationView(APIView):
    """
    POST /api/invitations/accept/
    Authenticated endpoint (no X-Tenant header required).
    Body: {token}
    The authenticated user's email must match the invitation email (case-insensitive).
    Creates the Membership atomically. Single use.
    """

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Accept an invitation",
        request=AcceptInvitationSerializer,
        responses={201: {"type": "object", "properties": {"detail": {"type": "string"}}}},
    )
    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_token = serializer.validated_data["token"]
        token_hash = Invitation.hash_token(raw_token)

        try:
            with transaction.atomic():
                invitation = Invitation.objects.select_for_update().get(
                    token_hash=token_hash,
                    accepted_at__isnull=True,
                    revoked_at__isnull=True,
                )
                # Must not be expired.
                if invitation.is_expired:
                    raise ValidationError({"detail": _ACCEPT_ERROR})

                # Email must match the authenticated user's email (case-insensitive).
                if invitation.email.lower() != request.user.email.lower():
                    raise ValidationError({"detail": _ACCEPT_ERROR})

                # Create membership (may already exist if the user is somehow a member).
                try:
                    Membership.objects.create(
                        user=request.user,
                        tenant_id=invitation.tenant_id,
                        role=invitation.role,
                    )
                except IntegrityError as exc:
                    raise ValidationError(
                        {"detail": "You are already a member of this tenant."}
                    ) from exc

                invitation.accepted_at = timezone.now()
                invitation.save(update_fields=["accepted_at"])

        except Invitation.DoesNotExist as exc:
            raise ValidationError({"detail": _ACCEPT_ERROR}) from exc

        return Response(
            {"detail": "Invitation accepted. You have joined the workspace."},
            status=status.HTTP_201_CREATED,
        )
