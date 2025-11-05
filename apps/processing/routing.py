"""
WebSocket routing for processing app.

Defines WebSocket URL patterns for real-time communication:
- Upload progress tracking
- Processing status updates
- Error notifications
"""
from django.urls import path
from apps.processing.consumers import UploadProgressConsumer

websocket_urlpatterns = [
    path('ws/processing/<int:upload_id>/', UploadProgressConsumer.as_asgi()),
]
