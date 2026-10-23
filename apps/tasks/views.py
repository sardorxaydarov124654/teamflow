from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.common.calendar_utils import month_grid, parse_month

from apps.common.decorators import (
    company_member_required,
    company_scoped_queryset,
    manager_required,
    same_company_object,
)

from .forms import CommentForm, EmployeeTaskStatusForm, TaskForm
from .models import Task


def _notify_assignment(task):
    from apps.notifications.services import notify_user

    if task.assigned_to_id:
        notify_user(
            user=task.assigned_to,
            title="New task assigned",
            message=f'You were assigned to "{task.title}"',
            notif_type="task_assigned",
            extra={"task_id": task.id, "project_id": task.project_id},
        )


def _notify_status_change(task, actor=None):
    from apps.notifications.services import notify_user

    recipients = {task.created_by, task.assigned_to} - {None, actor}
    for recipient in recipients:
        notify_user(
            user=recipient,
            title="Task status updated",
            message=f'"{task.title}" is now {task.get_status_display()}',
            notif_type="task_status_changed",
            extra={"task_id": task.id, "status": task.status},
        )


def _notify_new_comment(comment):
    from apps.notifications.services import notify_user

    task = comment.task
    recipients = {task.created_by, task.assigned_to} - {None, comment.author}
    for recipient in recipients:
        notify_user(
            user=recipient,
            title="New comment",
            message=f'{comment.author.full_name} commented on "{task.title}"',
            notif_type="comment_added",
            extra={"task_id": task.id, "comment_id": comment.id},
        )


@company_member_required
def task_list_view(request):
    qs = company_scoped_queryset(
        request.user,
        Task.objects.select_related("project", "company", "assigned_to", "created_by"),
    )

    status = request.GET.get("status")
    priority = request.GET.get("priority")
    project_id = request.GET.get("project")
    assigned_to = request.GET.get("assigned_to")
    mine = request.GET.get("mine") == "1"
    overdue = request.GET.get("overdue") == "1"
    search = request.GET.get("q")
    ordering = request.GET.get("ordering", "-created_at")

    if status:
        qs = qs.filter(status=status)
    if priority:
        qs = qs.filter(priority=priority)
    if project_id:
        qs = qs.filter(project_id=project_id)
    if assigned_to and assigned_to.isdigit():
        qs = qs.filter(assigned_to_id=assigned_to)
    if mine:
        qs = qs.filter(assigned_to=request.user)
    if overdue:
        qs = qs.filter(deadline__lt=timezone.now()).exclude(status=Task.Status.DONE)
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
    if ordering in {"priority", "-priority"}:
        # Alphabetical order of the stored codes is wrong (urgent < low < medium),
        # so rank the priorities explicitly.
        rank = Case(
            When(priority="low", then=Value(1)),
            When(priority="medium", then=Value(2)),
            When(priority="high", then=Value(3)),
            When(priority="urgent", then=Value(4)),
            output_field=IntegerField(),
        )
        qs = qs.annotate(priority_rank=rank).order_by(
            "-priority_rank" if ordering == "-priority" else "priority_rank"
        )
    elif ordering in {"deadline", "-deadline", "created_at", "-created_at"}:
        qs = qs.order_by(ordering)

    return render(
        request,
        "tasks/list.html",
        {
            "tasks": qs,
            "mine": mine,
            "overdue": overdue,
            "now": timezone.now(),
            "status_choices": Task.Status.choices,
            "priority_choices": Task.Priority.choices,
            "current_status": status or "",
            "current_priority": priority or "",
            "search": search or "",
            "ordering": ordering,
        },
    )


@company_member_required
def task_create_view(request):
    user = request.user
    if user.is_employee:
        raise PermissionDenied("Employees cannot create tasks.")
    company = user.company
    if company is None:
        messages.error(request, "You are not attached to a company.")
        return redirect("dashboard:dashboard")

    if request.method == "POST":
        form = TaskForm(request.POST, company=company)
        if form.is_valid():
            task = form.save(commit=False)
            task.company = company
            task.created_by = user
            task.save()
            _notify_assignment(task)
            messages.success(request, f'Task "{task.title}" created.')
            return redirect("tasks:detail", pk=task.pk)
    else:
        initial = {}
        if request.GET.get("project", "").isdigit():
            initial["project"] = request.GET["project"]
        form = TaskForm(company=company, initial=initial)
    return render(request, "tasks/form.html", {"form": form, "mode": "create"})


@company_member_required
def task_detail_view(request, pk):
    qs = company_scoped_queryset(
        request.user, Task.objects.select_related("project", "company", "assigned_to", "created_by")
    )
    task = get_object_or_404(qs, pk=pk)
    if not same_company_object(request.user, task):
        raise PermissionDenied

    comments = task.comments.select_related("author")

    if request.method == "POST":
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.task = task
            comment.company = task.company
            comment.author = request.user
            comment.save()
            _notify_new_comment(comment)
            messages.success(request, "Comment added.")
            return redirect("tasks:detail", pk=task.pk)
    else:
        comment_form = CommentForm()

    user = request.user
    can_change_status = user.is_manager or user.is_platform_admin or task.assigned_to_id == user.id
    return render(
        request,
        "tasks/detail.html",
        {
            "task": task,
            "comments": comments,
            "comment_form": comment_form,
            "can_change_status": can_change_status,
            "status_choices": Task.Status.choices,
            "is_overdue": bool(
                task.deadline and task.deadline < timezone.now() and task.status != Task.Status.DONE
            ),
        },
    )


@company_member_required
@require_POST
def task_status_view(request, pk):
    """Quick status change: managers/admins for any task, employees only for their own."""
    qs = company_scoped_queryset(request.user, Task.objects.all())
    task = get_object_or_404(qs, pk=pk)
    user = request.user
    if not (user.is_manager or user.is_platform_admin or task.assigned_to_id == user.id):
        raise PermissionDenied("You can only change the status of tasks assigned to you.")

    form = EmployeeTaskStatusForm(request.POST, instance=task)
    if form.is_valid():
        old_status = Task.objects.values_list("status", flat=True).get(pk=task.pk)
        task = form.save()
        if task.status != old_status:
            _notify_status_change(task, actor=user)
        messages.success(request, f"Status changed to {task.get_status_display()}.")
    else:
        messages.error(request, "Invalid status.")
    next_url = request.POST.get("next", "")
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("tasks:detail", pk=task.pk)


@company_member_required
def task_calendar_view(request):
    first_day = parse_month(request.GET.get("month"))
    qs = company_scoped_queryset(request.user, Task.objects.all())
    if request.GET.get("mine") == "1":
        qs = qs.filter(assigned_to=request.user)
    weeks, prev_month, next_month = month_grid(first_day, qs)
    return render(
        request,
        "tasks/calendar.html",
        {
            "weeks": weeks,
            "month": first_day,
            "prev_month": prev_month,
            "next_month": next_month,
            "mine": request.GET.get("mine") == "1",
            "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        },
    )


@manager_required
def task_edit_view(request, pk):
    qs = company_scoped_queryset(request.user, Task.objects.all())
    task = get_object_or_404(qs, pk=pk)
    if not same_company_object(request.user, task):
        raise PermissionDenied

    old_status = task.status
    old_assignee_id = task.assigned_to_id

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, company=task.company)
        if form.is_valid():
            task = form.save()
            if task.assigned_to_id and task.assigned_to_id != old_assignee_id:
                _notify_assignment(task)
            if task.status != old_status:
                _notify_status_change(task, actor=request.user)
            messages.success(request, "Task updated.")
            return redirect("tasks:detail", pk=task.pk)
    else:
        form = TaskForm(instance=task, company=task.company)
    return render(request, "tasks/form.html", {"form": form, "mode": "edit", "task": task})


@manager_required
def task_delete_view(request, pk):
    qs = company_scoped_queryset(request.user, Task.objects.all())
    task = get_object_or_404(qs, pk=pk)
    if not same_company_object(request.user, task):
        raise PermissionDenied
    if request.method == "POST":
        title = task.title
        task.delete()
        messages.success(request, f'Task "{title}" deleted.')
        return redirect("tasks:list")
    return render(request, "tasks/confirm_delete.html", {"task": task})
