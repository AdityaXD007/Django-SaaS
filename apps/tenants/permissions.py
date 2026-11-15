from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from .models import Membership, Tenant

TENANT_ACCESS_DENIED_DETAIL = "Tenant not found or access denied."

# Role hierarchy: higher index = more permissions.
_ROLE_HIERARCHY = [
    Membership.Role.MEMBER,
    Membership.Role.ADMIN,
    Membership.Role.OWNER,
]


def _role_level(role: str) -> int:
    """Return a numeric level for a role string; unknown roles get -1."""
    try:
        return _ROLE_HIERARCHY.index(role)
    except ValueError:
        return -1


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


def HasTenantRole(minimum_role: str) -> type:
    """
    Permission factory returning a class that requires the caller to hold at
    least *minimum_role* in the tenant resolved from the X-Tenant header.

    Role hierarchy (ascending): member < admin < owner.

    Usage::

        permission_classes = (IsAuthenticated, HasTenantRole("admin"))
    """

    class _HasTenantRole(BasePermission):
        message = TENANT_ACCESS_DENIED_DETAIL

        def has_permission(self, request, view):
            if getattr(view, "swagger_fake_view", False):
                return True
            _, membership = resolve_tenant_membership(request)
            if _role_level(membership.role) < _role_level(minimum_role):
                raise PermissionDenied(TENANT_ACCESS_DENIED_DETAIL)
            return True

    _HasTenantRole.__name__ = f"HasTenantRole_{minimum_role}"
    _HasTenantRole.__qualname__ = f"HasTenantRole_{minimum_role}"
    return _HasTenantRole


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
