"""
Tests for Phase 4 invitations:
- Create, duplicate pending, already-a-member blocked.
- Accept happy path, wrong email, expired, revoked, reuse.
- Token stored hashed, member-role cannot create invites.
- Schema generation produces no warnings.
"""

import hashlib
import secrets
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.invitations.models import Invitation
from apps.tenants.models import Membership
from apps.tenants.services import create_tenant_with_owner

User = get_user_model()

INVITATIONS_URL = "/api/tenants/current/invitations/"
ACCEPT_URL = "/api/invitations/accept/"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def enable_return_token(settings):
    settings.INVITATION_RETURN_TOKEN = True


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="inv_owner@example.com", password="Pass123!#", full_name="Inv Owner"
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="inv_admin@example.com", password="Pass123!#", full_name="Inv Admin"
    )


@pytest.fixture
def member_user(db):
    return User.objects.create_user(
        email="inv_member@example.com", password="Pass123!#", full_name="Inv Member"
    )


@pytest.fixture
def invitee(db):
    return User.objects.create_user(
        email="invitee@example.com", password="Pass123!#", full_name="Invitee"
    )


@pytest.fixture
def tenant(owner):
    return create_tenant_with_owner(user=owner, name="Invite Org")


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


def api_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_create_invitation(owner, tenant):
    client = api_client(owner)
    resp = client.post(
        INVITATIONS_URL,
        {"email": "newuser@example.com", "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert Invitation.objects.filter(tenant=tenant, email="newuser@example.com").exists()


@pytest.mark.django_db
def test_admin_can_create_invitation(admin_user, tenant, admin_membership):
    client = api_client(admin_user)
    resp = client.post(
        INVITATIONS_URL,
        {"email": "someone@example.com", "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_member_cannot_create_invitation(member_user, tenant, member_membership):
    client = api_client(member_user)
    resp = client.post(
        INVITATIONS_URL,
        {"email": "someone@example.com", "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_invite_role_owner_rejected(owner, tenant):
    """Invitations cannot grant the owner role."""
    client = api_client(owner)
    resp = client.post(
        INVITATIONS_URL,
        {"email": "someone@example.com", "role": "owner"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_duplicate_pending_invite_rejected(owner, tenant):
    client = api_client(owner)
    client.post(
        INVITATIONS_URL,
        {"email": "dup@example.com", "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    resp = client.post(
        INVITATIONS_URL,
        {"email": "dup@example.com", "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_already_a_member_rejected(owner, member_user, tenant, member_membership):
    client = api_client(owner)
    resp = client.post(
        INVITATIONS_URL,
        {"email": member_user.email, "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_token_stored_as_hash_only(owner, tenant):
    client = api_client(owner)
    resp = client.post(
        INVITATIONS_URL,
        {"email": "hashtest@example.com", "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_201_CREATED
    inv = Invitation.objects.get(tenant=tenant, email="hashtest@example.com")
    # token_hash must be a 64-char hex SHA-256 string, not a raw token
    assert len(inv.token_hash) == 64
    # It must not equal the raw token returned (if INVITATION_RETURN_TOKEN is True in test)
    if resp.data.get("token"):
        raw = resp.data["token"]
        assert inv.token_hash == hashlib.sha256(raw.encode()).hexdigest()
        assert inv.token_hash != raw


@pytest.mark.django_db
def test_token_only_in_response_when_return_token_setting_enabled(owner, tenant, settings):
    # When INVITATION_RETURN_TOKEN is False, token must NOT be returned in API response
    settings.INVITATION_RETURN_TOKEN = False
    client = api_client(owner)
    resp = client.post(
        INVITATIONS_URL,
        {"email": "nodebug@example.com", "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["token"] is None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_pending_invitations(owner, tenant):
    client = api_client(owner)
    client.post(
        INVITATIONS_URL,
        {"email": "list1@example.com", "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    client.post(
        INVITATIONS_URL,
        {"email": "list2@example.com", "role": "admin"},
        HTTP_X_TENANT=tenant.slug,
    )
    resp = client.get(INVITATIONS_URL, HTTP_X_TENANT=tenant.slug)
    assert resp.status_code == status.HTTP_200_OK
    emails = [i["email"] for i in resp.data]
    assert "list1@example.com" in emails
    assert "list2@example.com" in emails
    # Raw token must never appear in list response
    for item in resp.data:
        assert "token" not in item


# ---------------------------------------------------------------------------
# Revoke
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_revoke_invitation(owner, tenant):
    client = api_client(owner)
    create_resp = client.post(
        INVITATIONS_URL,
        {"email": "revoke@example.com", "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    inv_id = create_resp.data["id"]
    resp = client.delete(f"{INVITATIONS_URL}{inv_id}/", HTTP_X_TENANT=tenant.slug)
    assert resp.status_code == status.HTTP_204_NO_CONTENT
    inv = Invitation.objects.get(id=inv_id)
    assert inv.revoked_at is not None


# ---------------------------------------------------------------------------
# Accept — happy path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accept_invitation_happy_path(owner, invitee, tenant):
    # Create invitation for invitee's email
    client_owner = api_client(owner)
    create_resp = client_owner.post(
        INVITATIONS_URL,
        {"email": invitee.email, "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    assert create_resp.status_code == status.HTTP_201_CREATED
    raw_token = create_resp.data.get("token")
    assert raw_token is not None, "INVITATION_RETURN_TOKEN must be True; token must be in response"

    # Invitee accepts
    client_invitee = api_client(invitee)
    resp = client_invitee.post(ACCEPT_URL, {"token": raw_token})
    assert resp.status_code == status.HTTP_201_CREATED
    assert Membership.objects.filter(user=invitee, tenant=tenant).exists()

    # Mark invitation as accepted
    inv = Invitation.objects.get(tenant=tenant, email=invitee.email)
    assert inv.accepted_at is not None


# ---------------------------------------------------------------------------
# Accept — error cases
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accept_wrong_email(owner, invitee, member_user, tenant, member_membership):
    client_owner = api_client(owner)
    create_resp = client_owner.post(
        INVITATIONS_URL,
        {"email": invitee.email, "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    raw_token = create_resp.data.get("token")

    # member_user tries to use invitee's token
    client_member = api_client(member_user)
    resp = client_member.post(ACCEPT_URL, {"token": raw_token})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_accept_expired_invitation(owner, invitee, tenant):
    # Manually create an expired invitation
    raw_token = secrets.token_urlsafe(32)
    Invitation.objects.create(
        tenant=tenant,
        email=invitee.email,
        role=Invitation.Role.MEMBER,
        token_hash=Invitation.hash_token(raw_token),
        invited_by=owner,
        expires_at=timezone.now() - timedelta(days=1),
    )
    client = api_client(invitee)
    resp = client.post(ACCEPT_URL, {"token": raw_token})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_accept_revoked_invitation(owner, invitee, tenant):
    raw_token = secrets.token_urlsafe(32)
    Invitation.objects.create(
        tenant=tenant,
        email=invitee.email,
        role=Invitation.Role.MEMBER,
        token_hash=Invitation.hash_token(raw_token),
        invited_by=owner,
        expires_at=timezone.now() + timedelta(days=7),
        revoked_at=timezone.now(),
    )
    client = api_client(invitee)
    resp = client.post(ACCEPT_URL, {"token": raw_token})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_accept_invalid_token(invitee):
    client = api_client(invitee)
    resp = client.post(ACCEPT_URL, {"token": "completely-wrong-token"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_accept_already_accepted_invitation(owner, invitee, tenant):
    raw_token = secrets.token_urlsafe(32)
    Invitation.objects.create(
        tenant=tenant,
        email=invitee.email,
        role=Invitation.Role.MEMBER,
        token_hash=Invitation.hash_token(raw_token),
        invited_by=owner,
        expires_at=timezone.now() + timedelta(days=7),
        accepted_at=timezone.now(),
    )
    client = api_client(invitee)
    resp = client.post(ACCEPT_URL, {"token": raw_token})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_accept_token_single_use(owner, invitee, tenant):
    """After accepting once, a second accept attempt must fail."""
    client_owner = api_client(owner)
    create_resp = client_owner.post(
        INVITATIONS_URL,
        {"email": invitee.email, "role": "member"},
        HTTP_X_TENANT=tenant.slug,
    )
    raw_token = create_resp.data.get("token")

    client_invitee = api_client(invitee)
    client_invitee.post(ACCEPT_URL, {"token": raw_token})
    # Second attempt
    resp = client_invitee.post(ACCEPT_URL, {"token": raw_token})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
