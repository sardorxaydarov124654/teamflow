from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.decorators import company_member_required, manager_required

from .forms import CardForm
from .models import PaymentMethod, Subscription
from .services import PAID_CODES, apply_plan, ensure_plans, get_plan, limit_problem


def _payment_method(company):
    return PaymentMethod.objects.filter(company=company).first()


@company_member_required
def plans_list_view(request):
    """
    Billing page. Shows ONLY the two paid plans (Pro and Max): the plan the company
    currently has is marked, the other one is offered as an upgrade / switch.
    """
    company = request.user.company
    if company is None:
        return redirect("companies:platform-list")
    ensure_plans()
    plans = list(get_plan(c) for c in PAID_CODES)
    subscription = Subscription.objects.select_related("plan").filter(company=company).first()
    return render(
        request,
        "subscriptions/plans.html",
        {
            "plans": plans,
            "current_code": company.plan,
            "company": company,
            "subscription": subscription,
            "current_plan": get_plan(company.plan),
            "payment_method": _payment_method(company),
        },
    )


@company_member_required
def my_subscription_view(request):
    company = request.user.company
    if company is None:
        messages.info(request, "Platform admins do not have a subscription.")
        return redirect("companies:platform-list")

    ensure_plans()
    subscription = Subscription.objects.select_related("plan").filter(company=company).first()
    if subscription is None:
        subscription = apply_plan(company, get_plan(company.plan) or get_plan("free"))
    return render(
        request,
        "subscriptions/mine.html",
        {
            "subscription": subscription,
            "company": company,
            "member_count": company.members.filter(is_active=True).count(),
            "project_count": company.projects.count(),
            "payment_method": _payment_method(company),
        },
    )


@manager_required
def upgrade_view(request, plan_code):
    """Upgrade (Free→Pro/Max) or switch (Pro↔Max). Asks for a card when none is saved."""
    company = request.user.company
    if company is None:
        messages.error(request, "You are not attached to a company.")
        return redirect("dashboard:dashboard")
    if plan_code not in PAID_CODES:
        return redirect("subscriptions:plans")

    plan = get_plan(plan_code)
    if plan is None:
        return redirect("subscriptions:plans")
    if company.plan == plan.code:
        messages.info(request, f"You are already on the {plan.name} plan.")
        return redirect("subscriptions:plans")

    saved = _payment_method(company)
    use_new_card = saved is None or request.GET.get("new_card") == "1" or request.POST.get("new_card") == "1"
    is_switch = company.plan in PAID_CODES
    problem = limit_problem(company, plan)
    card_form = CardForm(request.POST or None) if use_new_card else None

    if request.method == "POST":
        if problem:
            messages.error(request, problem)
            return redirect("subscriptions:plans")
        if use_new_card and not card_form.is_valid():
            pass  # fall through and re-render with errors
        else:
            with transaction.atomic():
                if use_new_card:
                    card_form.save_for(company)
                apply_plan(company, plan)
            messages.success(
                request,
                f"Your company is now on the {plan.name} plan (mock billing — no real charge).",
            )
            return redirect("subscriptions:plans")

    return render(
        request,
        "subscriptions/confirm_upgrade.html",
        {
            "plan": plan,
            "company": company,
            "is_switch": is_switch,
            "current_plan": get_plan(company.plan),
            "saved_card": saved,
            "use_new_card": use_new_card,
            "card_form": card_form,
            "problem": problem,
        },
    )


@manager_required
def card_update_view(request):
    """Add or replace the company's payment card without changing the plan."""
    company = request.user.company
    if company is None:
        return redirect("dashboard:dashboard")
    form = CardForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save_for(company)
        messages.success(request, "Payment card saved.")
        return redirect("subscriptions:plans")
    return render(
        request,
        "subscriptions/card_form.html",
        {"form": form, "saved_card": _payment_method(company)},
    )
