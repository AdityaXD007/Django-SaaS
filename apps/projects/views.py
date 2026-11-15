"""
apps/projects/views.py — ProjectViewSet

REFERENCE PATTERN for tenant-scoped resources
==============================================
To add your own tenant-scoped resource:

1. Create a model that inherits ``TenantScopedModel`` (see apps/tenants/models.py).
2. Create a ViewSet that mixes in ``TenantScopedViewSetMixin`` **before** the DRF base.
3. Set ``permission_classes`` using ``IsTenantMember`` / ``HasTenantRole`` as needed
   and override ``get_permissions()`` for action-level differentiation.
4. Keep ``tenant`` and ``created_by`` in ``read_only_fields`` on the serializer so
   clients cannot move rows between tenants or forge authorship.
5. Register the ViewSet with a router and include it in ``config/urls.py``.
"""

from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from apps.tenants.mixins import TenantScopedViewSetMixin
from apps.tenants.permissions import HasTenantRole, IsTenantMember

from .models import Project
from .serializers import ProjectSerializer


class ProjectViewSet(TenantScopedViewSetMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin, mixins.DestroyModelMixin,
                     mixins.ListModelMixin, GenericViewSet):
    """
    Tenant-scoped Project resource.

    - Any tenant member may list, retrieve, create, and update projects.
    - Only admins and owners may delete projects.
    - ``tenant`` and ``created_by`` are always read-only; a client sending
      ``tenant`` in the payload cannot move a project to another tenant.
    """

    queryset = Project.objects.select_related("created_by", "tenant").all()
    serializer_class = ProjectSerializer

    def get_permissions(self):
        if self.action == "destroy":
            return [IsAuthenticated(), HasTenantRole("admin")()]
        return [IsAuthenticated(), IsTenantMember()]

    def perform_create(self, serializer):
        # TenantScopedViewSetMixin.perform_create stamps tenant; we also stamp created_by.
        serializer.save(tenant=self.request.tenant, created_by=self.request.user)
