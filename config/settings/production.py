import os

from .base import *  # noqa: F401,F403

# In production the SECRET_KEY must come from the environment.
if SECRET_KEY.startswith("django-insecure"):  # noqa: F405
    raise RuntimeError("Set a real SECRET_KEY in the environment for production.")

DEBUG = False

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LOGGING["root"]["level"] = "WARNING"  # noqa: F405

# SECRET_KEY security
if SECRET_KEY.startswith("django-insecure"):  # noqa: F405
    raise RuntimeError(
        "Set a real SECRET_KEY in the environment for production."
    )

DEBUG = False

# Render domain
RENDER_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

if RENDER_HOST:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, RENDER_HOST]  # noqa: F405
    CSRF_TRUSTED_ORIGINS = [
        *CSRF_TRUSTED_ORIGINS,  # noqa: F405
        f"https://{RENDER_HOST}",
    ]

# HTTPS security
SECURE_SSL_REDIRECT = env.bool(  # noqa: F405
    "SECURE_SSL_REDIRECT",
    default=True,
)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

# WhiteNoise static files
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Logging
LOGGING["root"]["level"] = "WARNING"  # noqa: F405
