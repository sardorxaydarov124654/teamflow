import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()  # must be created before importing routing

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from apps.notifications.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # Session-based auth: the browser's normal Django session cookie is
        # reused for the WebSocket handshake, same as any other page request.
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
