from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from .models import Membership, Tenant

TENANT_ACCESS_DENIED_DETAIL = "Tenant not found or access denied."


def resolve_tenant_membership(request):
    if hasattr(request, "tenant") and hasattr(request, "membership"):
        return request.tenant, request.membership

    tenant_slug = request.headers.get("X-Tenant") or request.META.get("HTTP_X_TENANT")
    if not tenant_slug or not request.user or not request.user.is_authenticated:
        raise PermissionDenied(TENANT_ACCESS_DENIED_DETAIL)

    tenant = Tenant.objects.filter(slug=tenant_slug, is_active=True).first()
    if not tenant:
        raise PermissionDenied(TENANT_ACCESS_DENIED_DETAIL)

    membership = Membership.objects.filter(tenant=tenant, user=request.user).first()
    if not membership:
        raise PermissionDenied(TENANT_ACCESS_DENIED_DETAIL)

    request.tenant = tenant
    request.membership = membership
    return tenant, membership


class IsTenantMember(BasePermission):
    message = TENANT_ACCESS_DENIED_DETAIL

    def has_permission(self, request, view):
        if getattr(view, "swagger_fake_view", False):
            return True
        resolve_tenant_membership(request)
        return True


class IsTenantAdmin(BasePermission):
    message = TENANT_ACCESS_DENIED_DETAIL

    def has_permission(self, request, view):
        if getattr(view, "swagger_fake_view", False):
            return True
        _, membership = resolve_tenant_membership(request)
        if membership.role not in (Membership.Role.OWNER, Membership.Role.ADMIN):
            raise PermissionDenied(TENANT_ACCESS_DENIED_DETAIL)
        return True
