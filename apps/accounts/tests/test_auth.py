import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.tenants.models import Membership, Tenant

User = get_user_model()


@pytest.mark.django_db
def test_register_creates_user_tenant_owner_membership_and_tokens():
    client = APIClient()
    payload = {
        "email": "Owner@Example.Com",
        "password": "StrongPassword123!#",
        "full_name": "Workspace Owner",
        "tenant_name": "Rocket Startups",
    }
    response = client.post("/api/auth/register/", payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    data = response.data
    assert "user" in data
    assert "tenant" in data
    assert "access" in data
    assert "refresh" in data

    # Verify user saved with lowercase email
    user = User.objects.get(email="owner@example.com")
    assert user.full_name == "Workspace Owner"
    assert user.is_active is True

    # Verify tenant created
    tenant = Tenant.objects.get(slug="rocket-startups")
    assert tenant.name == "Rocket Startups"

    # Verify owner membership created
    membership = Membership.objects.get(user=user, tenant=tenant)
    assert membership.role == Membership.Role.OWNER


@pytest.mark.django_db
def test_register_duplicate_email_case_insensitive_rejected():
    client = APIClient()
    payload = {
        "email": "first@example.com",
        "password": "StrongPassword123!#",
        "full_name": "First User",
        "tenant_name": "First Workspace",
    }
    res1 = client.post("/api/auth/register/", payload, format="json")
    assert res1.status_code == status.HTTP_201_CREATED

    duplicate_payload = {
        "email": "FIRST@EXAMPLE.COM",
        "password": "StrongPassword123!#",
        "full_name": "Duplicate User",
        "tenant_name": "Second Workspace",
    }
    res2 = client.post("/api/auth/register/", duplicate_payload, format="json")
    assert res2.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in res2.data


@pytest.mark.django_db
def test_register_weak_password_rejected():
    client = APIClient()
    payload = {
        "email": "weak@example.com",
        "password": "123",
        "full_name": "Weak User",
        "tenant_name": "Weak Workspace",
    }
    response = client.post("/api/auth/register/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password" in response.data


@pytest.mark.django_db
def test_same_tenant_name_gets_distinct_slugs():
    client = APIClient()
    payload1 = {
        "email": "alice@example.com",
        "password": "StrongPassword123!#",
        "full_name": "Alice",
        "tenant_name": "Acme Corp",
    }
    res1 = client.post("/api/auth/register/", payload1, format="json")
    assert res1.status_code == status.HTTP_201_CREATED
    assert res1.data["tenant"]["slug"] == "acme-corp"

    payload2 = {
        "email": "bob@example.com",
        "password": "StrongPassword123!#",
        "full_name": "Bob",
        "tenant_name": "Acme Corp",
    }
    res2 = client.post("/api/auth/register/", payload2, format="json")
    assert res2.status_code == status.HTTP_201_CREATED
    assert res2.data["tenant"]["slug"] == "acme-corp-1"


@pytest.mark.django_db
def test_login_by_email_works():
    client = APIClient()
    register_payload = {
        "email": "loginuser@example.com",
        "password": "StrongPassword123!#",
        "full_name": "Login User",
        "tenant_name": "Login Workspace",
    }
    client.post("/api/auth/register/", register_payload, format="json")

    login_payload = {
        "email": "loginuser@example.com",
        "password": "StrongPassword123!#",
    }
    response = client.post("/api/auth/token/", login_payload, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert "refresh" in response.data


@pytest.mark.django_db
def test_me_requires_auth():
    client = APIClient()
    unauthenticated_res = client.get("/api/auth/me/")
    assert unauthenticated_res.status_code == status.HTTP_401_UNAUTHORIZED

    register_payload = {
        "email": "me_user@example.com",
        "password": "StrongPassword123!#",
        "full_name": "Me User",
        "tenant_name": "Me Workspace",
    }
    reg_res = client.post("/api/auth/register/", register_payload, format="json")
    access_token = reg_res.data["access"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    auth_res = client.get("/api/auth/me/")
    assert auth_res.status_code == status.HTTP_200_OK
    data = auth_res.data
    assert data["email"] == "me_user@example.com"
    assert data["full_name"] == "Me User"
    assert len(data["memberships"]) == 1
    assert data["memberships"][0]["tenant"]["name"] == "Me Workspace"
    assert data["memberships"][0]["role"] == "owner"
