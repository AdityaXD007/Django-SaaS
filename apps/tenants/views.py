from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Membership
from .permissions import IsTenantMember
from .serializers import TenantMemberSerializer, TenantSerializer


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
