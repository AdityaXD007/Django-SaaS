from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Membership
from .permissions import TENANT_ACCESS_DENIED_DETAIL, IsTenantMember
from .serializers import MemberRoleUpdateSerializer, TenantMemberSerializer, TenantSerializer

LAST_OWNER_MSG = "Cannot remove or demote the last owner of this tenant."
OWNER_PROTECTED_MSG = "Only an owner can modify or remove another owner, or grant the owner role."


def _get_scoped_membership(request, membership_id):
    """Return the Membership for membership_id scoped to request.tenant, or 404."""
    try:
        return Membership.objects.select_related("user").get(
            id=membership_id, tenant=request.tenant
        )
    except Membership.DoesNotExist:
        from rest_framework.exceptions import NotFound

        raise NotFound() from None


def _owner_count(tenant):
    return Membership.objects.filter(tenant=tenant, role=Membership.Role.OWNER).count()


class TenantListView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="List user's workspaces",
        description="Returns all active tenants/workspaces where the caller holds a membership.",
        responses={200: TenantSerializer(many=True)},
    )
    def get(self, request):
        memberships = (
            Membership.objects.filter(user=request.user, tenant__is_active=True)
            .select_related("tenant")
            .order_by("-created_at")
        )
        workspaces = [
            {
                "id": str(m.tenant.id),
                "name": m.tenant.name,
                "slug": m.tenant.slug,
                "role": m.role,
                "is_active": m.tenant.is_active,
                "created_at": m.tenant.created_at,
            }
            for m in memberships
        ]
        return Response(workspaces, status=status.HTTP_200_OK)


class CurrentTenantMembersView(APIView):
    permission_classes = (IsAuthenticated, IsTenantMember)

    @extend_schema(
        summary="List members of current workspace",
        description="Returns all members in the workspace resolved via the X-Tenant header.",
        responses={200: TenantMemberSerializer(many=True)},
    )
    def get(self, request):
        members = (
            Membership.objects.filter(tenant=request.tenant)
            .select_related("user")
            .order_by("-created_at")
        )
        serializer = TenantMemberSerializer(members, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MembershipDetailView(APIView):
    """
    PATCH  /api/tenants/current/members/<id>/  — change role (admin/owner only).
    DELETE /api/tenants/current/members/<id>/  — remove member or self-leave.

    Rules:
    - Admins cannot modify/remove owners or grant the owner role.
    - The last remaining owner cannot be demoted or removed.
    - A member may remove themselves (leave) unless they are the last owner.
    """

    permission_classes = (IsAuthenticated, IsTenantMember)

    @extend_schema(
        summary="Update a membership's role",
        request=MemberRoleUpdateSerializer,
        responses={200: TenantMemberSerializer},
    )
    def patch(self, request, membership_id):
        caller_membership = request.membership
        target = _get_scoped_membership(request, membership_id)

        # Only admin/owner may change roles.
        if caller_membership.role not in (Membership.Role.OWNER, Membership.Role.ADMIN):
            raise PermissionDenied(TENANT_ACCESS_DENIED_DETAIL)

        serializer = MemberRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data["role"]

        # Admins cannot touch owners or grant the owner role.
        if caller_membership.role == Membership.Role.ADMIN:
            if target.role == Membership.Role.OWNER:
                raise PermissionDenied(OWNER_PROTECTED_MSG)
            if new_role == Membership.Role.OWNER:
                raise PermissionDenied(OWNER_PROTECTED_MSG)

        # Protect last owner from demotion.
        if target.role == Membership.Role.OWNER and new_role != Membership.Role.OWNER:
            if _owner_count(request.tenant) <= 1:
                raise ValidationError(LAST_OWNER_MSG)

        target.role = new_role
        target.save(update_fields=["role"])
        return Response(TenantMemberSerializer(target).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Remove a member or leave the workspace",
        responses={204: None},
    )
    def delete(self, request, membership_id):
        caller_membership = request.membership
        target = _get_scoped_membership(request, membership_id)

        is_self = target.user_id == request.user.id

        if not is_self:
            # Only admin/owner can remove others.
            if caller_membership.role not in (Membership.Role.OWNER, Membership.Role.ADMIN):
                raise PermissionDenied(TENANT_ACCESS_DENIED_DETAIL)
            # Admins cannot remove owners.
            if (
                caller_membership.role == Membership.Role.ADMIN
                and target.role == Membership.Role.OWNER
            ):
                raise PermissionDenied(OWNER_PROTECTED_MSG)

        # Protect last owner.
        if target.role == Membership.Role.OWNER and _owner_count(request.tenant) <= 1:
            raise ValidationError(LAST_OWNER_MSG)

        target.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
