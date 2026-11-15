from django.urls import path

from .views import AcceptInvitationView, TenantInvitationListCreateView, TenantInvitationRevokeView

app_name = "invitations"

# Tenant-scoped routes are mounted under /api/tenants/current/invitations/ from config/urls.py.
# The accept route is mounted under /api/invitations/accept/ (no X-Tenant header needed).

tenant_urlpatterns = [
    path("", TenantInvitationListCreateView.as_view(), name="invitation-list-create"),
    path(
        "<uuid:invitation_id>/",
        TenantInvitationRevokeView.as_view(),
        name="invitation-revoke",
    ),
]

urlpatterns = [
    path("accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
]
