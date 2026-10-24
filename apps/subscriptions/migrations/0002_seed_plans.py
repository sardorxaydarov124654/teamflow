from django.db import migrations

PLANS = [
    {
        "code": "free",
        "name": "Free",
        "max_users": 3,
        "max_projects": 5,
        "price_monthly": 0,
        "features": ["Up to 3 team members", "Up to 5 projects", "Task comments", "Email invitations"],
    },
    {
        "code": "pro",
        "name": "Pro",
        "max_users": 50,
        "max_projects": None,
        "price_monthly": 29,
        "features": ["Up to 50 team members", "Unlimited projects", "Real-time notifications", "Deadline reminders"],
    },
    {
        "code": "business",
        "name": "Business",
        "max_users": None,
        "max_projects": None,
        "price_monthly": 99,
        "features": ["Unlimited team members", "Unlimited projects", "Priority support", "Advanced reporting"],
    },
]


def seed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("subscriptions", "SubscriptionPlan")
    for data in PLANS:
        SubscriptionPlan.objects.update_or_create(code=data["code"], defaults=data)


def unseed_plans(apps, schema_editor):
    apps.get_model("subscriptions", "SubscriptionPlan").objects.filter(
        code__in=[p["code"] for p in PLANS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0001_initial")]
    operations = [migrations.RunPython(seed_plans, unseed_plans)]
