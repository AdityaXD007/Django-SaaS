"""
Tests for Phase 4 member management:
- Role PATCH, DELETE on /api/tenants/current/members/<id>/
- Role hierarchy, last-owner protection, self-leave, cross-tenant 404.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.tenants.models import Membership
from apps.tenants.services import create_tenant_with_owner

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="owner@example.com", password="Pass123!#", full_name="Owner"
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@example.com", password="Pass123!#", full_name="Admin"
    )


@pytest.fixture
def member_user(db):
    return User.objects.create_user(
        email="member@example.com", password="Pass123!#", full_name="Member"
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="other@example.com", password="Pass123!#", full_name="Other"
    )


@pytest.fixture
def tenant(owner):
    return create_tenant_with_owner(user=owner, name="Test Org")


@pytest.fixture
def admin_membership(admin_user, tenant):
    return Membership.objects.create(
        user=admin_user, tenant=tenant, role=Membership.Role.ADMIN
    )


@pytest.fixture
def member_membership(member_user, tenant):
    return Membership.objects.create(
        user=member_user, tenant=tenant, role=Membership.Role.MEMBER
    )


@pytest.fixture
def owner_membership(owner, tenant):
    return Membership.objects.get(user=owner, tenant=tenant)


def api_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


MEMBERS_URL = "/api/tenants/current/members/"


def member_detail_url(membership_id):
    return f"{MEMBERS_URL}{membership_id}/"


# ---------------------------------------------------------------------------
# PATCH — role change
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_change_member_role(owner, tenant, member_membership):
    client = api_client(owner)
    resp = client.patch(
        member_detail_url(member_membership.id),
        {"role": "admin"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_200_OK
    member_membership.refresh_from_db()
    assert member_membership.role == Membership.Role.ADMIN


@pytest.mark.django_db
def test_admin_can_change_member_role(admin_user, tenant, member_membership, admin_membership):
    client = api_client(admin_user)
    resp = client.patch(
        member_detail_url(member_membership.id),
        {"role": "admin"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_member_cannot_change_role(member_user, tenant, member_membership, admin_membership):
    client = api_client(member_user)
    resp = client.patch(
        member_detail_url(admin_membership.id),
        {"role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_cannot_modify_owner(admin_user, tenant, owner_membership, admin_membership):
    client = api_client(admin_user)
    resp = client.patch(
        member_detail_url(owner_membership.id),
        {"role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_cannot_grant_owner_role(admin_user, tenant, member_membership, admin_membership):
    client = api_client(admin_user)
    resp = client.patch(
        member_detail_url(member_membership.id),
        {"role": "owner"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_owner_can_grant_owner_role(owner, tenant, member_membership):
    client = api_client(owner)
    resp = client.patch(
        member_detail_url(member_membership.id),
        {"role": "owner"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_last_owner_cannot_be_demoted(owner, tenant, owner_membership):
    client = api_client(owner)
    resp = client.patch(
        member_detail_url(owner_membership.id),
        {"role": "admin"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_cross_tenant_membership_patch_returns_404(owner, admin_user, other_user):
    tenant_a = create_tenant_with_owner(user=owner, name="A Corp")
    tenant_b = create_tenant_with_owner(user=other_user, name="B Corp")
    # admin_user is in tenant_a as admin
    Membership.objects.create(
        user=admin_user, tenant=tenant_a, role=Membership.Role.ADMIN
    )
    # Try to PATCH a membership from tenant_b using tenant_a's slug
    b_owner_m = Membership.objects.get(user=other_user, tenant=tenant_b)
    client = api_client(owner)
    resp = client.patch(
        member_detail_url(b_owner_m.id),
        {"role": "member"},
        HTTP_X_TENANT=tenant_a.slug,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# DELETE — remove member / self-leave
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_remove_member(owner, tenant, member_membership):
    client = api_client(owner)
    resp = client.delete(
        member_detail_url(member_membership.id),
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT
    assert not Membership.objects.filter(id=member_membership.id).exists()


@pytest.mark.django_db
def test_admin_can_remove_member(admin_user, tenant, member_membership, admin_membership):
    client = api_client(admin_user)
    resp = client.delete(
        member_detail_url(member_membership.id),
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_admin_cannot_remove_owner(admin_user, tenant, owner_membership, admin_membership):
    client = api_client(admin_user)
    resp = client.delete(
        member_detail_url(owner_membership.id),
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_last_owner_cannot_be_removed(owner, tenant, owner_membership):
    client = api_client(owner)
    resp = client.delete(
        member_detail_url(owner_membership.id),
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_member_self_leave(member_user, tenant, member_membership):
    client = api_client(member_user)
    resp = client.delete(
        member_detail_url(member_membership.id),
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_member_cannot_remove_another_member(member_user, admin_user, tenant, member_membership):
    admin_m = Membership.objects.create(
        user=admin_user, tenant=tenant, role=Membership.Role.ADMIN
    )
    client = api_client(member_user)
    resp = client.delete(
        member_detail_url(admin_m.id),
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_cross_tenant_membership_delete_returns_404(owner, other_user):
    tenant_a = create_tenant_with_owner(user=owner, name="A Corp 2")
    tenant_b = create_tenant_with_owner(user=other_user, name="B Corp 2")
    b_owner_m = Membership.objects.get(user=other_user, tenant=tenant_b)
    client = api_client(owner)
    resp = client.delete(
        member_detail_url(b_owner_m.id),
        HTTP_X_TENANT=tenant_a.slug,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_last_owner_cannot_self_leave(owner, tenant, owner_membership):
    client = api_client(owner)
    resp = client.delete(
        member_detail_url(owner_membership.id),
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
