import pytest
from django.contrib.auth import get_user_model
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.viewsets import GenericViewSet

from apps.tenants.mixins import TenantScopedViewSetMixin
from apps.tenants.models import Membership, Tenant
from apps.tenants.permissions import TENANT_ACCESS_DENIED_DETAIL, IsTenantAdmin
from apps.tenants.services import create_tenant_with_owner

User = get_user_model()


@pytest.fixture
def user_a(db):
    return User.objects.create_user(
        email="user_a@example.com",
        password="Password123!#",
        full_name="User A",
    )


@pytest.fixture
def user_b(db):
    return User.objects.create_user(
        email="user_b@example.com",
        password="Password123!#",
        full_name="User B",
    )


@pytest.fixture
def tenant_a(user_a):
    return create_tenant_with_owner(user=user_a, name="Alpha Corp")


@pytest.fixture
def tenant_b(user_b):
    return create_tenant_with_owner(user=user_b, name="Beta Inc")


@pytest.mark.django_db
def test_tenants_list_only_callers_workspaces(user_a, user_b, tenant_a, tenant_b):
    # user_a is owner in tenant_a, and let's add user_a as member in another tenant_c
    tenant_c = Tenant.objects.create(name="Gamma Shared", slug="gamma-shared")
    Membership.objects.create(user=user_a, tenant=tenant_c, role=Membership.Role.MEMBER)

    client = APIClient()
    client.force_authenticate(user=user_a)

    response = client.get("/api/tenants/")
    assert response.status_code == status.HTTP_200_OK
    slugs = [item["slug"] for item in response.data]

    assert tenant_a.slug in slugs
    assert tenant_c.slug in slugs
    # Must NOT contain user_b's tenant
    assert tenant_b.slug not in slugs


@pytest.mark.django_db
def test_current_tenant_members_requires_header(user_a, tenant_a):
    client = APIClient()
    client.force_authenticate(user=user_a)

    # Missing X-Tenant header
    response = client.get("/api/tenants/current/members/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["detail"] == TENANT_ACCESS_DENIED_DETAIL


@pytest.mark.django_db
def test_cannot_access_foreign_tenant_slug(user_a, tenant_b):
    client = APIClient()
    client.force_authenticate(user=user_a)

    # Calling with tenant_b's slug where user_a has no membership
    response = client.get(
        "/api/tenants/current/members/",
        HTTP_X_TENANT=tenant_b.slug,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["detail"] == TENANT_ACCESS_DENIED_DETAIL


@pytest.mark.django_db
def test_nonexistent_tenant_slug_returns_same_403(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)

    response = client.get(
        "/api/tenants/current/members/",
        HTTP_X_TENANT="does-not-exist",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["detail"] == TENANT_ACCESS_DENIED_DETAIL


@pytest.mark.django_db
def test_current_tenant_members_success(user_a, user_b, tenant_a):
    Membership.objects.create(
        user=user_b,
        tenant=tenant_a,
        role=Membership.Role.MEMBER,
    )

    client = APIClient()
    client.force_authenticate(user=user_a)

    response = client.get(
        "/api/tenants/current/members/",
        HTTP_X_TENANT=tenant_a.slug,
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 2

    emails = [m["user"]["email"] for m in response.data]
    assert user_a.email in emails
    assert user_b.email in emails


@pytest.mark.django_db
def test_is_tenant_admin_permission(user_a, user_b, tenant_a):
    # user_a is owner, user_b is regular member
    Membership.objects.create(
        user=user_b,
        tenant=tenant_a,
        role=Membership.Role.MEMBER,
    )

    factory = APIRequestFactory()

    # Member check
    req_member = factory.get("/", HTTP_X_TENANT=tenant_a.slug)
    req_member.user = user_b
    perm = IsTenantAdmin()

    with pytest.raises(Exception) as exc_info:
        perm.has_permission(req_member, None)
    assert TENANT_ACCESS_DENIED_DETAIL in str(exc_info.value)

    # Owner check (passes)
    req_owner = factory.get("/", HTTP_X_TENANT=tenant_a.slug)
    req_owner.user = user_a
    assert perm.has_permission(req_owner, None) is True


@pytest.mark.django_db
def test_tenant_scoped_viewset_mixin(user_a, tenant_a):
    class DummySerializer(serializers.Serializer):
        pass

    class DummyViewSet(TenantScopedViewSetMixin, GenericViewSet):
        serializer_class = DummySerializer
        queryset = Membership.objects.all()

        def list(self, request):
            return Response([])

    viewset = DummyViewSet()
    factory = APIRequestFactory()

    # Normal request
    req = factory.get("/")
    req.tenant = tenant_a
    viewset.request = req

    qs = viewset.get_queryset()
    for item in qs:
        assert item.tenant == tenant_a

    # Swagger fake view request
    viewset.swagger_fake_view = True
    fake_qs = viewset.get_queryset()
    assert fake_qs.count() == 0
