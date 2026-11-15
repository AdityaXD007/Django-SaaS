from django.db import transaction
from django.utils.text import slugify

from .models import Membership, Tenant


def generate_unique_slug(name: str) -> str:
    base_slug = slugify(name) or "tenant"
    slug = base_slug
    counter = 1
    while Tenant.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


@transaction.atomic
def create_tenant_with_owner(user, name: str) -> Tenant:
    slug = generate_unique_slug(name)
    tenant = Tenant.objects.create(name=name, slug=slug)
    Membership.objects.create(
        user=user,
        tenant=tenant,
        role=Membership.Role.OWNER,
    )
    return tenant
