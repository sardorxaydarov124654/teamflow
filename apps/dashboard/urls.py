from django.urls import path

from .views import dashboard_view, home_view, report_view, search_view

app_name = "dashboard"

urlpatterns = [
    path("", home_view, name="home"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("reports/", report_view, name="report"),
    path("search/", search_view, name="search"),
]
