from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User


class EmailAuthenticationForm(AuthenticationForm):
    """AuthenticationForm already keys off USERNAME_FIELD ('email' here)."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_active:
            raise forms.ValidationError("This account is disabled.", code="inactive")


class RegisterForm(forms.Form):
    """
    Self-service registration. The registering user becomes the OWNER of a
    brand new Company (role=manager) — this is how tenants get created.
    """

    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm password")
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    company_name = forms.CharField(
        max_length=255,
        required=False,
        label="Company name",
        help_text=(
            "Optional. Leave it empty to join as an Employee without a company — "
            "a company manager can invite you later."
        ),
    )
    plan = forms.ChoiceField(
        choices=[("free", "Free"), ("pro", "Pro"), ("max", "Max")],
        initial="free",
        required=False,
        widget=forms.RadioSelect,
    )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        password_validation.validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password_confirm"):
            if cleaned["password"] != cleaned["password_confirm"]:
                self.add_error("password_confirm", "Passwords do not match.")
        return cleaned


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "avatar"]


class InviteMemberForm(forms.Form):
    email = forms.EmailField()
    # Managers can only invite EMPLOYEES into their own company, so there is no role field.


class MemberRoleForm(forms.ModelForm):
    """
    Edit a teammate's role / active flag.

    Security rules (privilege-escalation protection):
      * only a Platform Admin may hand out the Platform Admin role;
      * a manager cannot change their own role/state or the company owner's.
    """

    class Meta:
        model = User
        fields = ["role", "is_active"]

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        member = self.instance
        actor_is_admin = bool(actor and actor.is_platform_admin)

        # Platform Admin is never assignable from the team screen.
        self.fields["role"].choices = [
            (User.Role.MANAGER, "Manager"),
            (User.Role.EMPLOYEE, "Employee"),
        ]

        protected = bool(
            actor
            and not actor_is_admin
            and (
                member.pk == actor.pk
                or (member.company_id and member.company.owner_id == member.pk)
            )
        )
        if protected:
            self.fields["role"].disabled = True
            self.fields["is_active"].disabled = True
