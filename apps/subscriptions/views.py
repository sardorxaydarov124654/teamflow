from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.decorators import company_member_required, manager_required

from .models import Subscription, SubscriptionPlan


def _free_plan():
    plan, _ = SubscriptionPlan.objects.get_or_create(
        code="free",
        defaults={"name": "Free", "max_users": 3, "max_projects": 5, "price_monthly": 0},
    )
    return plan


@company_member_required
def plans_list_view(request):
    plans = SubscriptionPlan.objects.all()
    current_code = request.user.company.plan if request.user.company_id else None
    return render(
        request,
        "subscriptions/plans.html",
        {"plans": plans, "current_code": current_code},
    )


@company_member_required
def my_subscription_view(request):
    company = request.user.company
    if company is None:
        messages.info(request, "Platform admins do not have a subscription.")
        return redirect("companies:platform-list")

    subscription = Subscription.objects.select_related("plan").filter(company=company).first()
    if subscription is None:
        subscription = Subscription.objects.create(
            company=company,
            plan=SubscriptionPlan.objects.filter(code=company.plan).first() or _free_plan(),
        )
    return render(
        request,
        "subscriptions/mine.html",
        {
            "subscription": subscription,
            "company": company,
            "member_count": company.members.filter(is_active=True).count(),
            "project_count": company.projects.count(),
        },
    )


@manager_required
def upgrade_view(request, plan_code):
    company = request.user.company
    if company is None:
        messages.error(request, "You are not attached to a company.")
        return redirect("dashboard:dashboard")

    plan = get_object_or_404(SubscriptionPlan, code=plan_code)
    subscription, _ = Subscription.objects.get_or_create(
        company=company, defaults={"plan": _free_plan()}
    )
    if request.method == "POST":
        subscription.plan = plan
        subscription.save(update_fields=["plan"])
        subscription.sync_company_plan()
        messages.success(
            request,
            f"Your company is now on the {plan.name} plan (mock billing - no real charge).",
        )
        return redirect("subscriptions:mine")
    return render(
        request,
        "subscriptions/confirm_upgrade.html",
        {"plan": plan, "subscription": subscription, "company": company},
    )
