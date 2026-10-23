"""Helpers shared by the test-suites."""
from apps.accounts.models import User
from apps.companies.models import Company

PASSWORD = "StrongPass123!"


def make_company(name, owner_email):
    owner = User.objects.create_user(
        email=owner_email, password=PASSWORD, role=User.Role.MANAGER, first_name="Owner"
    )
    company = Company.objects.create(name=name, owner=owner)
    owner.company = company
    owner.save()
    return company, owner


def make_employee(company, email):
    return User.objects.create_user(
        email=email, password=PASSWORD, role=User.Role.EMPLOYEE, company=company
    )
