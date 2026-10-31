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

    def test_register_without_company_name_creates_plain_employee(self):
        resp = self.client.post(
            reverse("accounts:register"),
            {"email": "solo@x.com", "password": PASSWORD, "password_confirm": PASSWORD,
             "company_name": "", "plan": "free"},
        )
        self.assertRedirects(resp, reverse("dashboard:dashboard"))
        user = User.objects.get(email="solo@x.com")
        self.assertEqual(user.role, User.Role.EMPLOYEE)
        self.assertIsNone(user.company)
        self.assertFalse(Company.objects.exists())
        page = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "not part of a company yet")

    def test_paid_plan_requires_company_name(self):
        resp = self.client.post(
            reverse("accounts:register"),
            {"email": "solo@x.com", "password": PASSWORD, "password_confirm": PASSWORD,
             "company_name": "", "plan": "pro"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "required for a paid plan")
        self.assertFalse(User.objects.filter(email="solo@x.com").exists())

    def test_companyless_employee_no_loop_and_cannot_become_manager(self):
        User.objects.create_user(email="lone@x.com", password=PASSWORD, role=User.Role.EMPLOYEE)
        self.client.login(email="lone@x.com", password=PASSWORD)
        page = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Create my own company")
        for name in ("projects:list", "tasks:list", "accounts:members"):
            self.assertRedirects(self.client.get(reverse(name)), reverse("dashboard:dashboard"))
        # the old self-service company creation endpoint is gone
        for url in ("/companies/create/", "/company/create/"):
            self.assertEqual(self.client.post(url, {"name": "Solo"}).status_code, 404)
        user = User.objects.get(email="lone@x.com")
        self.assertEqual(user.role, User.Role.EMPLOYEE)
        self.assertIsNone(user.company)
        self.assertFalse(Company.objects.exists())

    def test_company_profile_redirects_companyless_user(self):
        User.objects.create_user(email="lone@x.com", password=PASSWORD, role=User.Role.EMPLOYEE)
        self.client.login(email="lone@x.com", password=PASSWORD)
        self.assertRedirects(self.client.get(reverse("companies:profile")), reverse("dashboard:dashboard"))


class RolePermissionTests(TestCase):
    def setUp(self):
        self.company, self.manager = make_company("Company A", "manager@a.com")
        self.employee = make_employee(self.company, "employee@a.com")

    def test_manager_can_invite_and_invitation_can_be_accepted(self):
        self.client.login(email="manager@a.com", password=PASSWORD)
        resp = self.client.post(
            reverse("accounts:invite-member"), {"email": "New@A.com"}
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

    def test_invite_always_creates_employee_even_if_role_is_forged(self):
        self.client.login(email="manager@a.com", password=PASSWORD)
        self.client.post(reverse("accounts:invite-member"), {"email": "x@a.com", "role": "manager"})
        self.assertEqual(CompanyInvitation.objects.get(email="x@a.com").role, User.Role.EMPLOYEE)
        self.assertNotContains(self.client.get(reverse("accounts:invite-member")), 'name="role"')

    def test_platform_admin_cannot_invite(self):
        User.objects.create_superuser(email="root@x.com", password=PASSWORD)
        self.client.login(email="root@x.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("accounts:invite-member")).status_code, 403)

    def test_companyless_employee_can_be_invited_and_joins(self):
        lone = User.objects.create_user(email="lone@x.com", password=PASSWORD, role=User.Role.EMPLOYEE)
        self.client.login(email="manager@a.com", password=PASSWORD)
        self.client.post(reverse("accounts:invite-member"), {"email": "lone@x.com"})
        inv = CompanyInvitation.objects.get(email="lone@x.com")
        self.client.logout()
        url = reverse("accounts:accept-invitation", args=[inv.token])
        self.assertEqual(self.client.get(url).status_code, 302)  # must sign in first
        self.client.login(email="lone@x.com", password=PASSWORD)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url)
        lone.refresh_from_db()
        self.assertEqual(lone.company, self.company)
        self.assertEqual(lone.role, User.Role.EMPLOYEE)

    def test_employee_of_other_company_cannot_be_invited(self):
        make_company("B", "b@b.com")
        self.client.login(email="manager@a.com", password=PASSWORD)
        resp = self.client.post(reverse("accounts:invite-member"), {"email": "b@b.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CompanyInvitation.objects.filter(email="b@b.com").exists())

    def test_team_list_has_no_platform_admins_and_managers_first(self):
        admin = User.objects.create_superuser(email="root@x.com", password=PASSWORD)
        admin.company = self.company
        admin.save()
        self.client.login(email="manager@a.com", password=PASSWORD)
        resp = self.client.get(reverse("accounts:members"))
        self.assertNotContains(resp, "root@x.com")
        self.assertNotContains(resp, "Platform Admin")
        emails = [m.email for m in resp.context["members"]]
        self.assertEqual(emails, ["manager@a.com", "employee@a.com"])
        self.assertEqual([r for r, _ in resp.context["role_choices"]], ["manager", "employee"])
        # filtering by the removed role finds nothing extra
        resp = self.client.get(reverse("accounts:members"), {"role": "platform_admin"})
        self.assertEqual(len(resp.context["members"]), 2)

    def test_platform_admin_team_screen_lists_company_users_only(self):
        User.objects.create_superuser(email="root@x.com", password=PASSWORD)
        User.objects.create_user(email="nocomp@x.com", password=PASSWORD, role=User.Role.EMPLOYEE)
        self.client.login(email="root@x.com", password=PASSWORD)
        resp = self.client.get(reverse("accounts:members"))
        emails = {m.email for m in resp.context["members"]}
        self.assertNotIn("root@x.com", emails)
        self.assertNotIn("nocomp@x.com", emails)
        self.assertIn("manager@a.com", emails)

    def test_company_name_and_logo_only_on_dashboard_and_settings(self):
        for email in ("manager@a.com", "employee@a.com"):
            self.client.login(email=email, password=PASSWORD)
            # other pages: plain greeting in the header, no company name/logo
            for name in ("projects:list", "tasks:list", "accounts:members", "notifications:list"):
                page = self.client.get(reverse(name))
                self.assertNotContains(page, "company-title")
                self.assertNotContains(page, "company-banner")
                self.assertNotContains(page, "default-company.svg")
                self.assertContains(page, "Welcome back")
            self.assertNotContains(self.client.get(reverse("accounts:profile")), "Company A")
            # dashboard: banner with logo + company name
            dash = self.client.get(reverse("dashboard:dashboard"))
            self.assertContains(dash, "default-company.svg")
            self.assertContains(dash, 'class="company-banner-name">Company A<')
            # settings: the same banner
            sett = self.client.get(reverse("companies:settings"))
            self.assertContains(sett, 'class="company-banner-name">Company A<')
            self.assertContains(sett, "default-company.svg")
            self.client.logout()

    def test_old_company_profile_url_redirects_to_settings(self):
        self.client.login(email="manager@a.com", password=PASSWORD)
        self.assertRedirects(self.client.get(reverse("companies:profile")), reverse("companies:settings"))

    def test_static_assets_are_versioned_against_stale_cache(self):
        self.client.login(email="manager@a.com", password=PASSWORD)
        page = self.client.get(reverse("dashboard:dashboard"))
        self.assertRegex(page.content.decode(), r"styles\.css\?v=\d+")

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
