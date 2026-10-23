from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("apps.dashboard.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.companies.urls")),
    path("", include("apps.projects.urls")),
    path("", include("apps.tasks.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.subscriptions.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Serve static files straight from the app/static folders (no collectstatic needed
    # in development, also works when running under uvicorn).
    urlpatterns += staticfiles_urlpatterns()

handler403 = "django.views.defaults.permission_denied"
