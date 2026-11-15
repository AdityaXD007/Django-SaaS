import hashlib
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.tenants.models import TenantScopedModel


class Invitation(TenantScopedModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    # Only the SHA-256 hash of the raw token is stored; the raw token is shown once.
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_invitations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "invitations"
        ordering = ("-created_at",)
        constraints = (
            # Partial unique constraint: at most one *pending* invitation per (tenant, email).
            # Pending = not accepted and not revoked.
            models.UniqueConstraint(
                fields=["tenant", "email"],
                condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="unique_pending_invitation_per_tenant_email",
            ),
        )

    def __str__(self) -> str:
        return f"Invitation({self.email} -> {self.tenant_id})"

    @property
    def is_pending(self) -> bool:
        return self.accepted_at is None and self.revoked_at is None

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()
