from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.common.testing import PASSWORD, make_company, make_employee
from apps.companies.models import Company

from .models import PaymentMethod, Subscription
from .services import ensure_plans

VISA = "4242 4242 4242 4242"
CARD = {"card_number": VISA, "holder_name": "jane doe", "expiry": "12/45", "cvv": "123"}
REG = {"email": "new@x.com", "password": PASSWORD, "password_confirm": PASSWORD, "company_name": "NewCo"}


class RegistrationWithPlanTests(TestCase):
    def test_free_registration_needs_no_card(self):
        resp = self.client.post(reverse("accounts:register"), {**REG, "plan": "free"})
        self.assertRedirects(resp, reverse("dashboard:dashboard"))
        company = User.objects.get(email="new@x.com").company
        self.assertEqual(company.plan, "free")
        self.assertFalse(PaymentMethod.objects.exists())

    def test_paid_registration_without_card_is_rejected(self):
        resp = self.client.post(reverse("accounts:register"), {**REG, "plan": "pro"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(email="new@x.com").exists())
        self.assertContains(resp, "required")

    def test_invalid_card_rejected(self):
        bad = {**CARD, "card_number": "4242 4242 4242 4241"}  # fails Luhn
        resp = self.client.post(reverse("accounts:register"), {**REG, "plan": "pro", **bad})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(email="new@x.com").exists())
        expired = {**CARD, "expiry": "01/20"}
        resp = self.client.post(reverse("accounts:register"), {**REG, "plan": "max", **expired})
        self.assertFalse(User.objects.filter(email="new@x.com").exists())

    def test_paid_registration_saves_only_safe_card_data(self):
        resp = self.client.post(reverse("accounts:register"), {**REG, "plan": "pro", **CARD})
        self.assertRedirects(resp, reverse("dashboard:dashboard"))
        company = User.objects.get(email="new@x.com").company
        self.assertEqual(company.plan, "pro")
        self.assertEqual(company.subscription_record.plan.code, "pro")
        pm = company.payment_method
        self.assertEqual((pm.brand, pm.last4, pm.holder_name), ("Visa", "4242", "JANE DOE"))
        # the full number / CVV must not exist anywhere on the model
        dump = " ".join(str(getattr(pm, f.name)) for f in pm._meta.fields)
        self.assertNotIn("4242424242424242", dump)
        self.assertNotIn("123", pm.last4)

    def test_register_page_shows_plan_picker_and_card_fields(self):
        resp = self.client.get(reverse("accounts:register") + "?plan=max")
        self.assertContains(resp, 'value="max"')
        self.assertContains(resp, "Card number")
        self.assertEqual(resp.context["selected"], "max")

    def test_landing_pricing_links_carry_plan(self):
        resp = self.client.get("/")
        for code in ("free", "pro", "max"):
            self.assertContains(resp, f"?plan={code}")


class BillingTests(TestCase):
    def setUp(self):
        self.company, self.manager = make_company("A", "m@a.com")
        self.employee = make_employee(self.company, "e@a.com")
        self.client.login(email="m@a.com", password=PASSWORD)

    def test_billing_shows_only_pro_and_max_even_without_seeded_plans(self):
        from .models import SubscriptionPlan
        SubscriptionPlan.objects.all().delete()  # simulates un-migrated DB
        resp = self.client.get(reverse("subscriptions:plans"))
        self.assertEqual([p.code for p in resp.context["plans"]], ["pro", "max"])
        self.assertContains(resp, "$29")
        self.assertContains(resp, "$99")
        self.assertContains(resp, "Upgrade to Pro")

    def test_upgrade_from_free_asks_for_card(self):
        resp = self.client.get(reverse("subscriptions:upgrade", args=["pro"]))
        self.assertContains(resp, "Card number")
        # POST without card -> not upgraded
        self.client.post(reverse("subscriptions:upgrade", args=["pro"]), {"new_card": "1"})
        self.company.refresh_from_db()
        self.assertEqual(self.company.plan, "free")
        # POST with card -> upgraded
        self.client.post(reverse("subscriptions:upgrade", args=["pro"]), {"new_card": "1", **CARD})
        self.company.refresh_from_db()
        self.assertEqual(self.company.plan, "pro")
        self.assertIsNone(self.company.get_project_limit())
        self.assertEqual(self.company.payment_method.last4, "4242")

    def test_switch_pro_to_max_and_back_uses_saved_card(self):
        self.client.post(reverse("subscriptions:upgrade", args=["pro"]), {"new_card": "1", **CARD})
        page = self.client.get(reverse("subscriptions:plans"))
        self.assertContains(page, "Current plan")
        self.assertContains(page, "Switch to Max")
        # saved card: confirmation page has no card fields
        confirm = self.client.get(reverse("subscriptions:upgrade", args=["max"]))
        self.assertNotContains(confirm, "Card number")
        self.assertContains(confirm, "4242")
        self.client.post(reverse("subscriptions:upgrade", args=["max"]))
        self.company.refresh_from_db()
        self.assertEqual(self.company.plan, "max")
        self.assertContains(self.client.get(reverse("subscriptions:plans")), "Switch to Pro")
        self.client.post(reverse("subscriptions:upgrade", args=["pro"]))
        self.company.refresh_from_db()
        self.assertEqual(self.company.plan, "pro")
        self.assertEqual(Subscription.objects.get(company=self.company).plan.code, "pro")

    def test_cannot_switch_to_plan_below_current_usage(self):
        self.client.post(reverse("subscriptions:upgrade", args=["max"]), {"new_card": "1", **CARD})
        for i in range(51):
            User.objects.create_user(email=f"u{i}@a.com", password=PASSWORD, company=self.company)
        self.client.post(reverse("subscriptions:upgrade", args=["pro"]))
        self.company.refresh_from_db()
        self.assertEqual(self.company.plan, "max")

    def test_employee_cannot_change_plan_or_card(self):
        self.client.logout()
        self.client.login(email="e@a.com", password=PASSWORD)
        self.assertEqual(self.client.post(reverse("subscriptions:upgrade", args=["pro"]), CARD).status_code, 403)
        self.assertEqual(self.client.get(reverse("subscriptions:card")).status_code, 403)

    def test_card_update_and_other_pages(self):
        resp = self.client.post(reverse("subscriptions:card"), {**CARD, "card_number": "8600 1234 5678 9014"})
        # 8600... may fail Luhn; either way page must respond without error
        self.assertIn(resp.status_code, (200, 302))
        self.client.post(reverse("subscriptions:card"), CARD)
        self.assertEqual(self.company.payment_method.last4, "4242")
        for name in ("subscriptions:mine", "subscriptions:plans", "subscriptions:card"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_business_plan_renamed_to_max(self):
        ensure_plans()
        self.assertEqual(Company.Plan.MAX, "max")
