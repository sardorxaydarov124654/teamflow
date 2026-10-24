from django.contrib import admin
from django.utils.html import format_html

from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "logo_thumbnail",
        "name",
        "slug",
        "owner",
        "plan",
        "is_active",
        "description_preview",
        "member_count",
        "project_count",
        "created_at",
    )
    list_filter = ("plan", "is_active", "created_at")
    search_fields = ("name", "slug", "owner__email", "description")
    readonly_fields = ("id", "created_at", "updated_at", "logo_preview")
    prepopulated_fields = {"slug": ("name",)}
    actions = ["activate_companies", "deactivate_companies"]

    fieldsets = (
        (None, {"fields": ("id", "name", "slug", "owner", "plan", "is_active")}),
        (
            "Company profile",
            {
                "description": "Shown on the dashboard and the company profile page.",
                "fields": ("description", "logo", "logo_preview"),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def member_count(self, obj):
        return obj.members.count()

    def project_count(self, obj):
        return obj.projects.count()

    @admin.display(description="Description")
    def description_preview(self, obj):
        return obj.get_description_preview(12) or "—"

    @admin.display(description="Logo")
    def logo_thumbnail(self, obj):
        if not obj.logo:
            return "—"
        return format_html(
            '<img src="{}" style="width:28px;height:28px;object-fit:cover;'
            'border-radius:6px;border:1px solid #DDE3DD;">',
            obj.logo.url,
        )

    @admin.display(description="Logo preview")
    def logo_preview(self, obj):
        if not obj.logo:
            return "No logo uploaded."
        return format_html(
            '<img src="{}" style="max-width:180px;max-height:180px;object-fit:contain;'
            'border-radius:8px;border:1px solid #DDE3DD;">',
            obj.logo.url,
        )

    @admin.action(description="Activate selected companies")
    def activate_companies(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Deactivate selected companies")
    def deactivate_companies(self, request, queryset):
        queryset.update(is_active=False)
