import calendar
from collections import defaultdict
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.common.calendar_utils import month_grid, parse_month
from apps.common.decorators import company_member_required, company_scoped_queryset
from apps.projects.models import Project
from apps.subscriptions.models import SubscriptionPlan
from apps.tasks.models import Comment, Task

CACHE_TTL_SECONDS = 60  # short TTL: stats stay fresh, DB still gets protected from bursts

DEFAULT_PLANS = [
    {
        "code": "free", "name": "Free", "price_monthly": 0, "max_users": 3, "max_projects": 5,
        "features": ["Up to 3 team members", "Up to 5 projects", "Task comments", "Email invitations"],
    },
    {
        "code": "pro", "name": "Pro", "price_monthly": 29, "max_users": 50, "max_projects": None,
        "features": ["Up to 50 team members", "Unlimited projects", "Real-time notifications", "Deadline reminders"],
    },
    {
        "code": "business", "name": "Business", "price_monthly": 99, "max_users": None, "max_projects": None,
        "features": ["Unlimited team members", "Unlimited projects", "Priority support", "Advanced reporting"],
    },
]


def home_view(request):
    """Public landing page for visitors; signed-in users go straight to the dashboard."""
    if request.user.is_authenticated:
        return redirect("dashboard:dashboard")
    plans = list(SubscriptionPlan.objects.all()) or DEFAULT_PLANS
    return render(request, "dashboard/home.html", {"plans": plans})


@company_member_required
def dashboard_view(request):
    user = request.user
    company = user.company
    if company is None:
        # Platform admins with no tenant land on the cross-company view instead.
        return redirect("companies:platform-list")

    cache_key = f"dashboard:v2:company:{company.id}"
    data = cache.get(cache_key)
    if data is None:
        data = _compute_stats(company)
        cache.set(cache_key, data, CACHE_TTL_SECONDS)

    # Per-request (not cached) widgets: calendar, activity feed, personal numbers.
    first_day = parse_month(request.GET.get("month"))
    tasks_qs = Task.objects.filter(company=company)
    weeks, prev_month, next_month = month_grid(first_day, tasks_qs)

    context = {
        "stats": data,
        "company": company,
        "weeks": weeks,
        "month": first_day,
        "prev_month": prev_month,
        "next_month": next_month,
        "weekdays": ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
        "activity": _recent_activity(company),
        "my_tasks": tasks_qs.filter(assigned_to=user)
        .exclude(status=Task.Status.DONE)
        .select_related("project")
        .order_by("deadline")[:5],
        "now": timezone.now(),
    }
    return render(request, "dashboard/dashboard.html", context)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def _compute_stats(company):
    projects = Project.objects.filter(company=company)
    tasks = Task.objects.filter(company=company)
    now = timezone.now()

    total = tasks.count()
    completed = tasks.filter(status=Task.Status.DONE).count()
    in_progress = tasks.filter(status__in=[Task.Status.IN_PROGRESS, Task.Status.REVIEW]).count()
    overdue = tasks.filter(deadline__lt=now).exclude(status=Task.Status.DONE).count()

    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "in_progress_tasks": in_progress,
        "todo_tasks": tasks.filter(status=Task.Status.TODO).count(),
        "overdue_tasks": overdue,
        "pending_tasks": total - completed,
        "completion_rate": round(completed * 100 / total) if total else 0,
        "total_employees": company.members.filter(is_active=True).count(),
        "active_projects": projects.filter(status=Project.Status.ACTIVE).count(),
        "completed_projects": projects.filter(status=Project.Status.COMPLETED).count(),
        "total_projects": projects.count(),
        "employee_productivity": _employee_productivity(company),
        "chart": _chart_series(tasks),
        "generated_at": now,
    }


def _employee_productivity(company):
    rows = (
        company.members.filter(is_active=True)
        .annotate(
            assigned=Count("assigned_tasks", distinct=True),
            completed=Count(
                "assigned_tasks",
                filter=Q(assigned_tasks__status=Task.Status.DONE),
                distinct=True,
            ),
        )
        .order_by("-assigned", "first_name")
        .values("id", "first_name", "last_name", "email", "role", "assigned", "completed")
    )
    out = []
    for row in rows:
        row["full_name"] = f"{row['first_name']} {row['last_name']}".strip() or row["email"]
        row["initials"] = (
            (row["first_name"][:1] + row["last_name"][:1]).upper() or row["email"][:2].upper()
        )
        row["role_label"] = dict(
            [("platform_admin", "Platform Admin"), ("manager", "Manager"), ("employee", "Employee")]
        ).get(row["role"], row["role"])
        out.append(row)
    return out


def _chart_series(tasks):
    """
    Four ready-made bar-chart series for the "Project progress overview" card:
    year (12 months), month (days), week (7 days) and day (24 hours).
    Each bucket counts tasks *created* and tasks *completed*.
    """
    now = timezone.localtime()
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    created = defaultdict(int)
    done = defaultdict(int)
    rows = tasks.filter(
        Q(created_at__gte=year_start) | Q(status=Task.Status.DONE, updated_at__gte=year_start)
    ).values_list("created_at", "status", "updated_at")

    for created_at, status, updated_at in rows:
        c = timezone.localtime(created_at)
        created[c.date()] += 1
        created[(c.year, c.month)] += 1
        created[(c.date(), c.hour)] += 1
        if status == Task.Status.DONE:
            u = timezone.localtime(updated_at)
            done[u.date()] += 1
            done[(u.year, u.month)] += 1
            done[(u.date(), u.hour)] += 1

    today = now.date()
    # Year
    year = {
        "labels": [calendar.month_abbr[m] for m in range(1, 13)],
        "created": [created[(today.year, m)] for m in range(1, 13)],
        "done": [done[(today.year, m)] for m in range(1, 13)],
    }
    # Month (days of the current month)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    month_days = [today.replace(day=d) for d in range(1, days_in_month + 1)]
    month = {
        "labels": [str(d.day) for d in month_days],
        "created": [created[d] for d in month_days],
        "done": [done[d] for d in month_days],
    }
    # Week (last 7 days)
    week_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    week = {
        "labels": [d.strftime("%a") for d in week_days],
        "created": [created[d] for d in week_days],
        "done": [done[d] for d in week_days],
    }
    # Day (hours today)
    day = {
        "labels": [f"{h:02d}" for h in range(24)],
        "created": [created[(today, h)] for h in range(24)],
        "done": [done[(today, h)] for h in range(24)],
    }
    return {"year": year, "month": month, "week": week, "day": day}


def _recent_activity(company, limit=6):
    items = []
    for task in Task.objects.filter(company=company).select_related(
        "created_by", "project"
    ).order_by("-created_at")[:limit]:
        items.append(
            {
                "when": task.created_at,
                "who": task.created_by,
                "verb": "created task",
                "task": task,
                "tag": task.project.name,
            }
        )
    for task in Task.objects.filter(company=company, status=Task.Status.DONE).select_related(
        "assigned_to", "project"
    ).order_by("-updated_at")[:limit]:
        items.append(
            {
                "when": task.updated_at,
                "who": task.assigned_to,
                "verb": "completed task",
                "task": task,
                "tag": task.project.name,
            }
        )
    for comment in Comment.objects.filter(company=company).select_related(
        "author", "task", "task__project"
    ).order_by("-created_at")[:limit]:
        items.append(
            {
                "when": comment.created_at,
                "who": comment.author,
                "verb": "commented on",
                "task": comment.task,
                "tag": comment.task.project.name,
                "body": comment.body,
            }
        )
    items.sort(key=lambda i: i["when"], reverse=True)
    return items[:limit]


# ---------------------------------------------------------------------------
# Report page ("Project report" button)
# ---------------------------------------------------------------------------
@company_member_required
def report_view(request):
    user = request.user
    projects = company_scoped_queryset(
        user,
        Project.objects.select_related("owner").annotate(
            total=Count("tasks", distinct=True),
            done=Count("tasks", filter=Q(tasks__status="done"), distinct=True),
            in_progress=Count("tasks", filter=Q(tasks__status="in_progress"), distinct=True),
            review=Count("tasks", filter=Q(tasks__status="review"), distinct=True),
            todo=Count("tasks", filter=Q(tasks__status="todo"), distinct=True),
            overdue=Count(
                "tasks",
                filter=Q(tasks__deadline__lt=timezone.now()) & ~Q(tasks__status="done"),
                distinct=True,
            ),
        ),
    ).order_by("name")

    rows = []
    for p in projects:
        rows.append(
            {
                "project": p,
                "progress": round(p.done * 100 / p.total) if p.total else 0,
                "total": p.total,
                "done": p.done,
                "in_progress": p.in_progress + p.review,
                "todo": p.todo,
                "overdue": p.overdue,
            }
        )

    tasks = company_scoped_queryset(user, Task.objects.all())
    by_priority = {
        code: tasks.filter(priority=code).exclude(status="done").count()
        for code, _ in Task.Priority.choices
    }
    max_priority = max(by_priority.values()) if by_priority else 0

    company = user.company
    people = _employee_productivity(company) if company else []

    return render(
        request,
        "dashboard/report.html",
        {
            "rows": rows,
            "people": people,
            "priority_rows": [
                {"label": label, "code": code, "count": by_priority[code],
                 "pct": round(by_priority[code] * 100 / max_priority) if max_priority else 0}
                for code, label in Task.Priority.choices
            ],
            "total_tasks": tasks.count(),
            "done_tasks": tasks.filter(status="done").count(),
            "overdue_tasks": tasks.filter(deadline__lt=timezone.now()).exclude(status="done").count(),
            "generated_at": timezone.now(),
        },
    )


# ---------------------------------------------------------------------------
# Global search (header search box)
# ---------------------------------------------------------------------------
@company_member_required
def search_view(request):
    q = request.GET.get("q", "").strip()
    projects, tasks, members = [], [], []
    if q:
        user = request.user
        projects = company_scoped_queryset(user, Project.objects.all()).filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        )[:10]
        tasks = company_scoped_queryset(user, Task.objects.select_related("project")).filter(
            Q(title__icontains=q) | Q(description__icontains=q)
        )[:15]
        if user.company_id:
            members = user.company.members.filter(
                Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
            )[:10]
    return render(
        request,
        "dashboard/search.html",
        {"q": q, "projects": projects, "tasks": tasks, "members": members},
    )
