import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.text import Truncator, slugify

MAX_LOGO_SIZE_MB = 5
DESCRIPTION_PREVIEW_WORDS = 28


def validate_logo_size(file):
    """Reject logo uploads over MAX_LOGO_SIZE_MB, so a huge image can't bloat the panel."""
    limit_bytes = MAX_LOGO_SIZE_MB * 1024 * 1024
    if file.size > limit_bytes:
        raise ValidationError(f"Logo file is too large. Max size is {MAX_LOGO_SIZE_MB}MB.")


class Company(models.Model):
    """A tenant. Every business record in the system hangs off a Company."""

    class Plan(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro"
        BUSINESS = "business", "Business"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    logo = models.ImageField(
        upload_to="company_logos/",
        blank=True,
        null=True,
        help_text="PNG, JPG, WEBP or SVG, up to 5MB. Shown on the dashboard and company profile page.",
        validators=[
            FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp", "svg"]),
            validate_logo_size,
        ],
    )
    description = models.TextField(
        blank=True,
        help_text="A short summary of the company. Shown on the dashboard and company profile page.",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_companies",
    )
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    def get_description_preview(self, word_limit=DESCRIPTION_PREVIEW_WORDS):
        """Short, dashboard-friendly excerpt of the description."""
        if not self.description:
            return ""
        return Truncator(self.description).words(word_limit, truncate=" вЂ¦")

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)[:240]
            slug = base_slug
            i = 1
            while Company.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base_slug}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)
