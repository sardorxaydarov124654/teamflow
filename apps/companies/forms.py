from django import forms

from .models import Company


class CompanyForm(forms.ModelForm):
    """Used on the Company settings page to edit an existing company's profile."""

    class Meta:
        model = Company
        fields = ["name", "description", "logo"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Acme Inc."}),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "A short summary of what the company does. "
                    "Shown on the dashboard and company profile page.",
                }
            ),
            "logo": forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg,image/webp,image/svg+xml"}),
        }
        help_texts = {
            "logo": "PNG, JPG, WEBP or SVG, up to 5MB.",
        }
