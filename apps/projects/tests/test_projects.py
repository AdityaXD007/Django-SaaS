"""
Tests for Phase 4 Projects:
- Cross-tenant isolation: user A cannot access tenant B's projects.
- Cannot create into another tenant by sending tenant in body.
- Role matrix: member (list/retrieve/create/update), admin/owner (delete).
- Schema generation produces no warnings for the new endpoints.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.tenants.models import Membership
from apps.tenants.services import create_tenant_with_owner

User = get_user_model()

PROJECTS_URL = "/api/projects/"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def owner_a(db):
    return User.objects.create_user(
        email="proj_owner_a@example.com", password="Pass123!#", full_name="Owner A"
    )


@pytest.fixture
def owner_b(db):
    return User.objects.create_user(
        email="proj_owner_b@example.com", password="Pass123!#", full_name="Owner B"
    )


@pytest.fixture
def admin_a(db):
    return User.objects.create_user(
        email="proj_admin_a@example.com", password="Pass123!#", full_name="Admin A"
    )


@pytest.fixture
def member_a(db):
    return User.objects.create_user(
        email="proj_member_a@example.com", password="Pass123!#", full_name="Member A"
    )


@pytest.fixture
def tenant_a(owner_a):
    return create_tenant_with_owner(user=owner_a, name="Projects Org A")


@pytest.fixture
def tenant_b(owner_b):
    return create_tenant_with_owner(user=owner_b, name="Projects Org B")


@pytest.fixture
def admin_a_membership(admin_a, tenant_a):
    return Membership.objects.create(
        user=admin_a, tenant=tenant_a, role=Membership.Role.ADMIN
    )


@pytest.fixture
def member_a_membership(member_a, tenant_a):
    return Membership.objects.create(
        user=member_a, tenant=tenant_a, role=Membership.Role.MEMBER
    )


@pytest.fixture
def project_a(owner_a, tenant_a):
    return Project.objects.create(
        name="Project Alpha",
        description="In tenant A",
        tenant=tenant_a,
        created_by=owner_a,
    )


@pytest.fixture
def project_b(owner_b, tenant_b):
    return Project.objects.create(
        name="Project Beta",
        description="In tenant B",
        tenant=tenant_b,
        created_by=owner_b,
    )


def api_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_a_cannot_list_tenant_b_projects(owner_a, owner_b, tenant_a, tenant_b, project_b):
    client = api_client(owner_a)
    resp = client.get(PROJECTS_URL, HTTP_X_TENANT=tenant_a.slug)
    assert resp.status_code == status.HTTP_200_OK
    ids = [p["id"] for p in resp.data["results"]]
    assert str(project_b.id) not in ids


@pytest.mark.django_db
def test_user_a_cannot_retrieve_tenant_b_project(
    owner_a, tenant_a, project_b
):
    client = api_client(owner_a)
    resp = client.get(f"{PROJECTS_URL}{project_b.id}/", HTTP_X_TENANT=tenant_a.slug)
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_user_a_cannot_update_tenant_b_project(owner_a, tenant_a, project_b):
    client = api_client(owner_a)
    resp = client.patch(
        f"{PROJECTS_URL}{project_b.id}/",
        {"name": "Hacked"},
        HTTP_X_TENANT=tenant_a.slug,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_user_a_cannot_delete_tenant_b_project(owner_a, tenant_a, project_b):
    client = api_client(owner_a)
    resp = client.delete(f"{PROJECTS_URL}{project_b.id}/", HTTP_X_TENANT=tenant_a.slug)
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_cannot_create_into_another_tenant_via_body(owner_a, tenant_a, tenant_b):
    """Sending `tenant` in body must NOT move the row to tenant_b."""
    client = api_client(owner_a)
    resp = client.post(
        PROJECTS_URL,
        {"name": "Sneaky Project", "tenant": str(tenant_b.id)},
        HTTP_X_TENANT=tenant_a.slug,
    )
    assert resp.status_code == status.HTTP_201_CREATED
    proj = Project.objects.get(id=resp.data["id"])
    assert proj.tenant_id == tenant_a.id  # Must be scoped to tenant_a, not tenant_b


# ---------------------------------------------------------------------------
# Role matrix
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_member_can_list_projects(member_a, tenant_a, member_a_membership, project_a):
    client = api_client(member_a)
    resp = client.get(PROJECTS_URL, HTTP_X_TENANT=tenant_a.slug)
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_member_can_retrieve_project(member_a, tenant_a, member_a_membership, project_a):
    client = api_client(member_a)
    resp = client.get(f"{PROJECTS_URL}{project_a.id}/", HTTP_X_TENANT=tenant_a.slug)
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_member_can_create_project(member_a, tenant_a, member_a_membership):
    client = api_client(member_a)
    resp = client.post(
        PROJECTS_URL,
        {"name": "Member Project", "description": "created by member"},
        HTTP_X_TENANT=tenant_a.slug,
    )
    assert resp.status_code == status.HTTP_201_CREATED
    proj = Project.objects.get(id=resp.data["id"])
    assert proj.created_by == member_a
    assert proj.tenant == tenant_a


@pytest.mark.django_db
def test_member_can_update_project(member_a, tenant_a, member_a_membership, project_a):
    client = api_client(member_a)
    resp = client.patch(
        f"{PROJECTS_URL}{project_a.id}/",
        {"name": "Updated by member"},
        HTTP_X_TENANT=tenant_a.slug,
    )
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_member_cannot_delete_project(member_a, tenant_a, member_a_membership, project_a):
    client = api_client(member_a)
    resp = client.delete(f"{PROJECTS_URL}{project_a.id}/", HTTP_X_TENANT=tenant_a.slug)
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_can_delete_project(admin_a, tenant_a, admin_a_membership, project_a):
    client = api_client(admin_a)
    resp = client.delete(f"{PROJECTS_URL}{project_a.id}/", HTTP_X_TENANT=tenant_a.slug)
    assert resp.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_owner_can_delete_project(owner_a, tenant_a, project_a):
    client = api_client(owner_a)
    resp = client.delete(f"{PROJECTS_URL}{project_a.id}/", HTTP_X_TENANT=tenant_a.slug)
    assert resp.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_project_response_has_correct_tenant(owner_a, tenant_a, project_a):
    client = api_client(owner_a)
    resp = client.get(f"{PROJECTS_URL}{project_a.id}/", HTTP_X_TENANT=tenant_a.slug)
    assert resp.status_code == status.HTTP_200_OK
    assert str(resp.data["tenant"]) == str(tenant_a.id)
    assert str(resp.data["created_by"]) == str(owner_a.id)


# ---------------------------------------------------------------------------
# Schema generation (no warnings)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_schema_generation_no_errors():
    """Ensure drf-spectacular can generate the schema without crashing."""
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    # This raises if there are hard errors; warnings go to stderr but don't raise.
    call_command("spectacular", "--validate", "--fail-on-warn", stdout=out, stderr=StringIO())
