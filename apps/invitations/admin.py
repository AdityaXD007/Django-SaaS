from django.contrib import admin

from .models import Invitation


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "tenant", "role", "invited_by", "created_at", "expires_at")
    list_filter = ("role", "tenant")
    search_fields = ("email",)
    readonly_fields = ("token_hash",)
