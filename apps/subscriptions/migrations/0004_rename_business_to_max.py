from django.db import migrations

MAX_DATA = {
    "name": "Max", "price_monthly": 99, "max_users": None, "max_projects": None,
    "features": ["Unlimited team members", "Unlimited projects", "Priority support", "Advanced reporting"],
}


def business_to_max(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "SubscriptionPlan")
    Company = apps.get_model("companies", "Company")
    max_plan, _ = Plan.objects.update_or_create(code="max", defaults=MAX_DATA)
    Subscription = apps.get_model("subscriptions", "Subscription")
    Subscription.objects.filter(plan__code="business").update(plan=max_plan)
    Plan.objects.filter(code="business").delete()
    Company.objects.filter(plan="business").update(plan="max")


def max_to_business(apps, schema_editor):
    Company = apps.get_model("companies", "Company")
    Plan = apps.get_model("subscriptions", "SubscriptionPlan")
    Company.objects.filter(plan="max").update(plan="business")
    Plan.objects.filter(code="max").update(code="business", name="Business")


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0003_alter_subscriptionplan_code_paymentmethod"),
        ("companies", "0003_alter_company_plan"),
    ]
    operations = [migrations.RunPython(business_to_max, max_to_business)]
