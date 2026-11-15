from django.urls import path

from .views import CurrentTenantMembersView, MembershipDetailView, TenantListView

app_name = "tenants"

urlpatterns = [
    path("", TenantListView.as_view(), name="tenant-list"),
    path("current/members/", CurrentTenantMembersView.as_view(), name="current-tenant-members"),
    path(
        "current/members/<uuid:membership_id>/",
        MembershipDetailView.as_view(),
        name="membership-detail",
    ),
]
