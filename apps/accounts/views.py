import secrets

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import password_validation, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.common.decorators import company_member_required, manager_required
from apps.companies.models import Company

from .forms import (
    EmailAuthenticationForm,
    InviteMemberForm,
    MemberRoleForm,
    ProfileForm,
    RegisterForm,
)
from .models import CompanyInvitation, User
from .tasks import send_invitation_email


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:dashboard")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = User(
                    email=form.cleaned_data["email"],
                    first_name=form.cleaned_data.get("first_name", ""),
                    last_name=form.cleaned_data.get("last_name", ""),
                    role=User.Role.MANAGER,
                )
                user.set_password(form.cleaned_data["password"])
                user.save()
                company = Company.objects.create(
                    name=form.cleaned_data["company_name"], owner=user
                )
                user.company = company
                user.save(update_fields=["company"])
            auth_login(request, user)
            messages.success(request, f"Welcome to TeamFlow, {user.first_name or user.email}!")
            return redirect("dashboard:dashboard")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


@require_POST
def logout_view(request):
    auth_logout(request)
    messages.success(request, "You have been signed out.")
    return redirect("dashboard:home")


@login_required
def profile_view(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def password_change_view(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # keep the user signed in
            messages.success(request, "Password changed.")
            return redirect("accounts:profile")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "accounts/password_change.html", {"form": form})


@company_member_required
def members_list_view(request):
    user = request.user
    if user.is_platform_admin and user.company_id is None:
        members = User.objects.select_related("company")
    else:
        members = User.objects.select_related("company").filter(company_id=user.company_id)

    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    if q:
        from django.db.models import Q

        members = members.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    if role in {r for r, _ in User.Role.choices}:
        members = members.filter(role=role)

    invitations = []
    if (user.is_manager or user.is_platform_admin) and user.company_id:
        invitations = CompanyInvitation.objects.filter(
            company_id=user.company_id, status=CompanyInvitation.Status.PENDING
        )
    return render(
        request,
        "accounts/members_list.html",
        {
            "members": members,
            "invitations": invitations,
            "q": q,
            "current_role": role,
            "role_choices": User.Role.choices,
            "site_url": settings.SITE_URL.rstrip("/"),
        },
    )


@company_member_required
def member_detail_view(request, pk):
    user = request.user
    qs = User.objects.all() if user.is_platform_admin else User.objects.filter(company_id=user.company_id)
    member = get_object_or_404(qs, pk=pk)

    can_edit = user.is_manager or user.is_platform_admin
    if request.method == "POST" and can_edit:
        form = MemberRoleForm(request.POST, instance=member, actor=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"{member.full_name} updated.")
            return redirect("accounts:members")
    else:
        form = MemberRoleForm(instance=member, actor=user) if can_edit else None

    return render(
        request,
        "accounts/member_detail.html",
        {"member": member, "form": form, "can_edit": can_edit},
    )


@company_member_required
def member_deactivate_view(request, pk):
    user = request.user
    if not (user.is_manager or user.is_platform_admin):
        messages.error(request, "Only a manager can deactivate a teammate.")
        return redirect("accounts:members")
    qs = User.objects.all() if user.is_platform_admin else User.objects.filter(company_id=user.company_id)
    member = get_object_or_404(qs, pk=pk)
    if member.pk == user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("accounts:members")
    if member.company_id and member.company.owner_id == member.pk and not user.is_platform_admin:
        messages.error(request, "The company owner cannot be deactivated.")
        return redirect("accounts:members")
    if request.method == "POST":
        # Soft-delete: deactivate rather than hard-delete a teammate's account.
        member.is_active = False
        member.save(update_fields=["is_active"])
        messages.success(request, f"{member.full_name} has been deactivated.")
    return redirect("accounts:members")


@manager_required
def invite_member_view(request):
    if not request.user.company_id:
        messages.error(request, "You are not attached to a company.")
        return redirect("dashboard:dashboard")

    company = request.user.company
    if not company.can_add_user():
        messages.error(request, "Your subscription plan's user limit has been reached.")
        return redirect("accounts:members")

    if request.method == "POST":
        form = InviteMemberForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower()
            role = form.cleaned_data["role"]

            if User.objects.filter(email__iexact=email).exists():
                form.add_error("email", "A user with this email already exists.")
            else:
                invitation, _ = CompanyInvitation.objects.update_or_create(
                    company=company,
                    email=email,
                    status=CompanyInvitation.Status.PENDING,
                    defaults={
                        "role": role,
                        "invited_by": request.user,
                        "token": secrets.token_urlsafe(32),
                    },
                )
                send_invitation_email.delay(
                    invitation.email, company.name, invitation.token, invitation.role
                )
                messages.success(request, f"Invitation created for {email}.")
                return redirect("accounts:members")
    else:
        form = InviteMemberForm()
    return render(request, "accounts/invite_member.html", {"form": form})


@manager_required
@require_POST
def invitation_cancel_view(request, pk):
    qs = CompanyInvitation.objects.filter(status=CompanyInvitation.Status.PENDING)
    if not request.user.is_platform_admin:
        qs = qs.filter(company_id=request.user.company_id)
    invitation = get_object_or_404(qs, pk=pk)
    email = invitation.email
    invitation.delete()
    messages.success(request, f"Invitation for {email} cancelled.")
    return redirect("accounts:members")


def accept_invitation_view(request, token):
    invitation = get_object_or_404(
        CompanyInvitation, token=token, status=CompanyInvitation.Status.PENDING
    )
    if User.objects.filter(email__iexact=invitation.email).exists():
        messages.error(request, "An account with this email already exists. Please sign in.")
        return redirect("accounts:login")

    if request.method == "POST":
        password = request.POST.get("password", "")
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        error = None
        try:
            password_validation.validate_password(password)
        except ValidationError as exc:
            error = " ".join(exc.messages)
        if error is None and not invitation.company.can_add_user():
            error = "This company has reached its plan's user limit."
        if error:
            messages.error(request, error)
        else:
            with transaction.atomic():
                user = User(
                    email=invitation.email,
                    first_name=first_name,
                    last_name=last_name,
                    role=invitation.role,
                    company=invitation.company,
                )
                user.set_password(password)
                user.save()
                invitation.status = CompanyInvitation.Status.ACCEPTED
                invitation.save(update_fields=["status"])
            auth_login(request, user)
            messages.success(request, f"Welcome to {invitation.company.name}!")
            return redirect("dashboard:dashboard")
    return render(request, "accounts/accept_invitation.html", {"invitation": invitation})
