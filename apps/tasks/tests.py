from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.common.testing import PASSWORD, make_company, make_employee
from apps.notifications.models import Notification
from apps.projects.models import Project

from .models import Task


class ProjectTests(TestCase):
    def setUp(self):
        self.company, self.manager = make_company("A", "m@a.com")
        self.employee = make_employee(self.company, "e@a.com")
        self.other, self.other_owner = make_company("B", "o@b.com")

    def test_manager_project_crud(self):
        self.client.login(email="m@a.com", password=PASSWORD)
        resp = self.client.post(
            reverse("projects:create"), {"name": "Website", "description": "x", "status": "active"}
        )
        project = Project.objects.get(name="Website")
        self.assertRedirects(resp, reverse("projects:detail", args=[project.pk]))
        self.assertEqual(project.company, self.company)
        self.assertEqual(self.client.get(reverse("projects:list")).status_code, 200)
        self.client.post(reverse("projects:edit", args=[project.pk]), {"name": "Website 2", "status": "active"})
        project.refresh_from_db()
        self.assertEqual(project.name, "Website 2")
        self.client.post(reverse("projects:delete", args=[project.pk]))
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_employee_cannot_create_project(self):
        self.client.login(email="e@a.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("projects:create")).status_code, 403)

    def test_project_isolation(self):
        secret = Project.objects.create(name="Secret", company=self.other, owner=self.other_owner)
        self.client.login(email="m@a.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("projects:detail", args=[secret.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("projects:delete", args=[secret.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("projects:list")), "Secret")

    def test_free_plan_project_limit(self):
        for i in range(5):
            Project.objects.create(name=f"P{i}", company=self.company, owner=self.manager)
        self.client.login(email="m@a.com", password=PASSWORD)
        self.client.post(reverse("projects:create"), {"name": "Sixth", "status": "planning"})
        self.assertFalse(Project.objects.filter(name="Sixth").exists())


class TaskTests(TestCase):
    def setUp(self):
        self.company, self.manager = make_company("A", "m@a.com")
        self.employee = make_employee(self.company, "e@a.com")
        self.project = Project.objects.create(name="Web", company=self.company, owner=self.manager)
        self.other, self.other_owner = make_company("B", "o@b.com")
        self.other_project = Project.objects.create(name="Other", company=self.other, owner=self.other_owner)

    def _task(self, **kw):
        defaults = dict(title="Fix bug", project=self.project, company=self.company,
                        assigned_to=self.employee, created_by=self.manager)
        defaults.update(kw)
        return Task.objects.create(**defaults)

    def test_manager_creates_and_assigns_task_with_notification(self):
        self.client.login(email="m@a.com", password=PASSWORD)
        resp = self.client.post(
            reverse("tasks:create"),
            {"title": "Build homepage", "project": self.project.pk, "assigned_to": self.employee.pk,
             "priority": "high", "status": "todo"},
        )
        task = Task.objects.get(title="Build homepage")
        self.assertRedirects(resp, reverse("tasks:detail", args=[task.pk]))
        self.assertTrue(Notification.objects.filter(user=self.employee, type="task_assigned").exists())

    def test_cannot_create_task_in_foreign_project(self):
        self.client.login(email="m@a.com", password=PASSWORD)
        self.client.post(reverse("tasks:create"), {"title": "Evil", "project": self.other_project.pk,
                                                     "priority": "low", "status": "todo"})
        self.assertFalse(Task.objects.filter(title="Evil").exists())

    def test_employee_cannot_create_edit_delete(self):
        task = self._task()
        self.client.login(email="e@a.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("tasks:create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("tasks:edit", args=[task.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("tasks:delete", args=[task.pk])).status_code, 403)

    def test_employee_changes_status_of_own_task_only(self):
        mine, other = self._task(), self._task(title="Not mine", assigned_to=self.manager)
        self.client.login(email="e@a.com", password=PASSWORD)
        resp = self.client.post(reverse("tasks:status", args=[mine.pk]), {"status": "in_progress"})
        self.assertEqual(resp.status_code, 302)
        mine.refresh_from_db()
        self.assertEqual(mine.status, "in_progress")
        self.assertTrue(Notification.objects.filter(user=self.manager, type="task_status_changed").exists())
        self.assertEqual(self.client.post(reverse("tasks:status", args=[other.pk]), {"status": "done"}).status_code, 403)

    def test_comment_notifies_other_party(self):
        task = self._task()
        self.client.login(email="e@a.com", password=PASSWORD)
        self.client.post(reverse("tasks:detail", args=[task.pk]), {"body": "Almost done"})
        self.assertEqual(task.comments.count(), 1)
        self.assertTrue(Notification.objects.filter(user=self.manager, type="comment_added").exists())
        self.assertFalse(Notification.objects.filter(user=self.employee, type="comment_added").exists())

    def test_task_isolation(self):
        foreign = Task.objects.create(title="Foreign", project=self.other_project, company=self.other,
                                      created_by=self.other_owner)
        self.client.login(email="m@a.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("tasks:detail", args=[foreign.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("tasks:list")), "Foreign")

    def test_filters_search_and_priority_ordering(self):
        self._task(title="Urgent fix", priority="urgent")
        self._task(title="Low polish", priority="low", status="done")
        self._task(title="High thing", priority="high")
        self.client.login(email="m@a.com", password=PASSWORD)
        self.assertContains(self.client.get(reverse("tasks:list"), {"priority": "urgent"}), "Urgent fix")
        self.assertNotContains(self.client.get(reverse("tasks:list"), {"priority": "urgent"}), "Low polish")
        self.assertContains(self.client.get(reverse("tasks:list"), {"q": "polish"}), "Low polish")
        resp = self.client.get(reverse("tasks:list"), {"ordering": "-priority"})
        titles = [t.title for t in resp.context["tasks"]]
        self.assertEqual(titles, ["Urgent fix", "High thing", "Low polish"])

    def test_deadline_reminder_task(self):
        from .tasks import send_deadline_reminders

        self._task(deadline=timezone.now() + timedelta(hours=3))
        self.assertEqual(send_deadline_reminders(), 1)
        self.assertEqual(send_deadline_reminders(), 0)  # only once
        self.assertTrue(Notification.objects.filter(user=self.employee, type="deadline_reminder").exists())


class PagesSmokeTests(TestCase):
    """Every page of the site must render (HTTP 200) for a manager."""

    def test_all_pages_render(self):
        company, manager = make_company("A", "m@a.com")
        project = Project.objects.create(name="P", company=company, owner=manager)
        task = Task.objects.create(title="T", project=project, company=company, created_by=manager,
                                   assigned_to=manager, deadline=timezone.now() + timedelta(days=1))
        self.client.login(email="m@a.com", password=PASSWORD)
        urls = [
            reverse("dashboard:dashboard"), reverse("dashboard:report"), reverse("dashboard:search") + "?q=P",
            reverse("projects:list"), reverse("projects:create"), reverse("projects:detail", args=[project.pk]),
            reverse("projects:edit", args=[project.pk]), reverse("projects:delete", args=[project.pk]),
            reverse("tasks:list"), reverse("tasks:create"), reverse("tasks:detail", args=[task.pk]),
            reverse("tasks:edit", args=[task.pk]), reverse("tasks:delete", args=[task.pk]),
            reverse("tasks:calendar"), reverse("accounts:members"), reverse("accounts:invite-member"),
            reverse("accounts:member-detail", args=[manager.pk]), reverse("accounts:profile"),
            reverse("accounts:password-change"), reverse("notifications:list"),
            reverse("companies:settings"),
            reverse("subscriptions:plans"), reverse("subscriptions:mine"), reverse("subscriptions:upgrade", args=["pro"]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)
