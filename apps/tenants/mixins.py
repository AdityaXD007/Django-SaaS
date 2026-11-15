class TenantScopedViewSetMixin:
    """
    Mixin for ViewSets operating on models inheriting from TenantScopedModel.
    Scopes querysets by request.tenant and stamps tenant on create.
    """

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return super().get_queryset().none()
        qs = super().get_queryset()
        tenant = getattr(self.request, "tenant", None)
        if tenant is None:
            return qs.none()
        return qs.filter(tenant=tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)
