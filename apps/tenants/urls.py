from django.urls import path

from .views import CurrentTenantMembersView, TenantListView

app_name = "tenants"

urlpatterns = [
    path("", TenantListView.as_view(), name="tenant-list"),
    path("current/members/", CurrentTenantMembersView.as_view(), name="current-tenant-members"),
]
