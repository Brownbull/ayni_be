"""
ASGI config for AYNI Backend project.
Supports both HTTP and WebSocket connections.
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Initialize Django ASGI application early to ensure apps are loaded
django_asgi_app = get_asgi_application()

# Import routing after Django is initialized
from apps.processing import routing as processing_routing

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(
            processing_routing.websocket_urlpatterns
        )
    ),
})
