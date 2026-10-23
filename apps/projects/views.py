from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.common.decorators import (
    company_member_required,
    company_scoped_queryset,
    manager_required,
    same_company_object,
)

from .forms import ProjectForm
from .models import Project


@company_member_required
def project_list_view(request):
    qs = company_scoped_queryset(
        request.user,
        Project.objects.select_related("owner", "company").annotate(
            task_total=Count("tasks", distinct=True),
            task_done=Count("tasks", filter=Q(tasks__status="done"), distinct=True),
        ),
    )

    status = request.GET.get("status")
    search = request.GET.get("q")
    ordering = request.GET.get("ordering", "-created_at")

    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
    if ordering in {"created_at", "-created_at", "deadline", "-deadline", "name", "-name"}:
        qs = qs.order_by(ordering)

    return render(
        request,
        "projects/list.html",
        {
            "projects": qs,
            "today": timezone.localdate(),
            "status_choices": Project.Status.choices,
            "current_status": status or "",
            "search": search or "",
            "ordering": ordering,
        },
    )

