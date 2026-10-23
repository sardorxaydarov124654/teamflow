from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.common.testing import PASSWORD, make_company, make_employee
from apps.companies.models import Company

from .models import CompanyInvitation, User


class PublicPagesTests(TestCase):
    def test_landing_page_for_anonymous(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Create free workspace")

    def test_login_and_register_pages_render(self):
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 200)

    def test_private_pages_redirect_to_login(self):
        for name in ["dashboard:dashboard", "projects:list", "tasks:list", "accounts:members"]:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 302, name)
            self.assertIn("/accounts/login/", resp["Location"])

    def test_landing_redirects_authenticated_user(self):
        make_company("A", "a@a.com")
        self.client.login(email="a@a.com", password=PASSWORD)
        self.assertRedirects(self.client.get("/"), reverse("dashboard:dashboard"))


class AuthFlowTests(TestCase):
    def test_register_creates_user_and_company(self):
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "email": "Owner@Example.com",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
                "company_name": "Acme Inc",
            },
        )
        self.assertRedirects(resp, reverse("dashboard:dashboard"))
        user = User.objects.get(email="owner@example.com")
        self.assertEqual(user.role, User.Role.MANAGER)
        self.assertEqual(user.company.name, "Acme Inc")
        self.assertEqual(user.company.owner, user)

    def test_register_rejects_duplicate_email_and_weak_password(self):
        make_company("A", "a@a.com")
        resp = self.client.post(
            reverse("accounts:register"),
            {"email": "a@a.com", "password": "123", "password_confirm": "123", "company_name": "X"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.filter(email="a@a.com").count(), 1)
        self.assertFalse(Company.objects.filter(name="X").exists())

    def test_login_case_insensitive_and_wrong_password(self):
        make_company("A", "owner@a.com")
        bad = self.client.post(reverse("accounts:login"), {"username": "owner@a.com", "password": "nope"})
        self.assertEqual(bad.status_code, 200)
        good = self.client.post(
            reverse("accounts:login"), {"username": "owner@a.com", "password": PASSWORD}
        )
        self.assertRedirects(good, reverse("dashboard:dashboard"))

    def test_logout_requires_post(self):
        make_company("A", "owner@a.com")
        self.client.login(email="owner@a.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("accounts:logout")), "/")
        self.assertEqual(self.client.get(reverse("dashboard:dashboard")).status_code, 302)

    def test_user_without_company_is_sent_to_create_company_without_loop(self):
        User.objects.create_user(email="lone@x.com", password=PASSWORD, role=User.Role.EMPLOYEE)
        self.client.login(email="lone@x.com", password=PASSWORD)
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertRedirects(resp, reverse("companies:create"))
        resp = self.client.post(reverse("companies:create"), {"name": "Solo", "description": ""})
        self.assertRedirects(resp, reverse("dashboard:dashboard"))
        user = User.objects.get(email="lone@x.com")
        self.assertEqual(user.role, User.Role.MANAGER)
        self.assertEqual(user.company.name, "Solo")


class RolePermissionTests(TestCase):
    def setUp(self):
        self.company, self.manager = make_company("Company A", "manager@a.com")
        self.employee = make_employee(self.company, "employee@a.com")

    def test_manager_can_invite_and_invitation_can_be_accepted(self):
        self.client.login(email="manager@a.com", password=PASSWORD)
        resp = self.client.post(
            reverse("accounts:invite-member"), {"email": "New@A.com", "role": "employee"}
        )
        self.assertRedirects(resp, reverse("accounts:members"))
        inv = CompanyInvitation.objects.get(email="new@a.com")
        self.assertEqual(len(mail.outbox), 1)

        self.client.logout()
        resp = self.client.post(
            reverse("accounts:accept-invitation", args=[inv.token]),
            {"password": PASSWORD, "first_name": "New", "last_name": "Hire"},
        )
        self.assertRedirects(resp, reverse("dashboard:dashboard"))
        new = User.objects.get(email="new@a.com")
        self.assertEqual(new.company, self.company)
        self.assertEqual(new.role, User.Role.EMPLOYEE)

    def test_employee_cannot_invite(self):
        self.client.login(email="employee@a.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("accounts:invite-member")).status_code, 403)

    def test_employee_cannot_open_billing_upgrade(self):
        self.client.login(email="employee@a.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("subscriptions:upgrade", args=["pro"])).status_code, 403)

    def test_manager_cannot_grant_platform_admin(self):
        self.client.login(email="manager@a.com", password=PASSWORD)
        resp = self.client.post(
            reverse("accounts:member-detail", args=[self.employee.pk]),
            {"role": "platform_admin", "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 200)  # form error, not saved
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.role, User.Role.EMPLOYEE)

    def test_manager_can_change_employee_role(self):
        self.client.login(email="manager@a.com", password=PASSWORD)
        self.client.post(
            reverse("accounts:member-detail", args=[self.employee.pk]),
            {"role": "manager", "is_active": "on"},
        )
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.role, User.Role.MANAGER)

    def test_owner_and_self_cannot_be_deactivated(self):
        self.client.login(email="manager@a.com", password=PASSWORD)
        self.client.post(reverse("accounts:member-deactivate", args=[self.manager.pk]))
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_blocked_company_loses_access(self):
        self.company.is_active = False
        self.company.save()
        self.client.login(email="manager@a.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("projects:list")).status_code, 403)


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.a, self.owner_a = make_company("Company A", "owner@a.com")
        self.b, self.owner_b = make_company("Company B", "owner@b.com")

    def test_company_a_cannot_see_company_b_members(self):
        self.client.login(email="owner@a.com", password=PASSWORD)
        resp = self.client.get(reverse("accounts:members"))
        self.assertContains(resp, "owner@a.com")
        self.assertNotContains(resp, "owner@b.com")
        resp = self.client.get(reverse("accounts:member-detail", args=[self.owner_b.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_platform_admin_sees_all_companies(self):
        User.objects.create_superuser(email="root@x.com", password=PASSWORD)
        self.client.login(email="root@x.com", password=PASSWORD)
        resp = self.client.get(reverse("companies:platform-list"))
        self.assertContains(resp, "Company A")
        self.assertContains(resp, "Company B")
        self.client.logout()
        self.client.login(email="owner@a.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("companies:platform-list")).status_code, 403)
