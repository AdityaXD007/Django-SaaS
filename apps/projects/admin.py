from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "created_by", "created_at")
    list_filter = ("tenant",)
    search_fields = ("name",)
