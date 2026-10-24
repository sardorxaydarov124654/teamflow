from .models import Subscription, SubscriptionPlan

DEFAULT_PLANS = [
    {"code": "free", "name": "Free", "price_monthly": 0, "max_users": 3, "max_projects": 5,
     "features": ["Up to 3 team members", "Up to 5 projects", "Task comments", "Email invitations"]},
    {"code": "pro", "name": "Pro", "price_monthly": 29, "max_users": 50, "max_projects": None,
     "features": ["Up to 50 team members", "Unlimited projects", "Real-time notifications", "Deadline reminders"]},
    {"code": "max", "name": "Max", "price_monthly": 99, "max_users": None, "max_projects": None,
     "features": ["Unlimited team members", "Unlimited projects", "Priority support", "Advanced reporting"]},
]
PAID_CODES = ("pro", "max")


def ensure_plans():
    """
    Make sure the plan catalogue exists (e.g. when migrations were not re-run),
    so the billing page and landing page never render empty.
    """
    for data in DEFAULT_PLANS:
        SubscriptionPlan.objects.get_or_create(code=data["code"], defaults=data)
    return SubscriptionPlan.objects.all()


def get_plan(code):
    ensure_plans()
    return SubscriptionPlan.objects.filter(code=code).first()


def limit_problem(company, plan):
    """Return a human-readable reason why `company` cannot move to `plan`, else None."""
    members = company.members.filter(is_active=True).count()
    projects = company.projects.count()
    if plan.max_users is not None and members > plan.max_users:
        return (f"Your company has {members} active members but the {plan.name} plan allows "
                f"{plan.max_users}. Deactivate some members first.")
    if plan.max_projects is not None and projects > plan.max_projects:
        return (f"Your company has {projects} projects but the {plan.name} plan allows "
                f"{plan.max_projects}.")
    return None


def apply_plan(company, plan):
    """Create/update the company's subscription and sync the denormalised plan field."""
    subscription, _ = Subscription.objects.get_or_create(company=company, defaults={"plan": plan})
    subscription.plan = plan
    subscription.status = Subscription.Status.ACTIVE
    subscription.start_new_period() if plan.is_paid else setattr(subscription, "current_period_end", None)
    subscription.save()
    subscription.sync_company_plan()
    return subscription
