"""
WebSocket consumers for real-time upload progress updates.

This module provides WebSocket consumers for:
- Real-time CSV upload progress tracking
- Live processing status updates
- Error notifications
- Completion events
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.exceptions import ObjectDoesNotExist

from apps.processing.models import Upload
from apps.authentication.models import User

logger = logging.getLogger(__name__)


class UploadProgressConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time upload progress updates.

    URL: /ws/processing/<upload_id>/

    Authentication: Expects JWT token in query string (?token=<jwt_access_token>)
    or in the first message after connection.

    Messages sent to client:
    - progress: {"type": "progress", "percent": 45.2, "message": "Processing rows..."}
    - status: {"type": "status", "status": "processing", "message": "Validating CSV"}
    - error: {"type": "error", "message": "Processing failed", "details": "..."}
    - complete: {"type": "complete", "message": "Upload complete", "results": {...}}
    """

    async def connect(self):
        """Handle WebSocket connection."""
        self.upload_id = self.scope['url_route']['kwargs']['upload_id']
        self.room_group_name = f'upload_{self.upload_id}'
        self.user = None

        # Try to authenticate from query string
        query_string = self.scope.get('query_string', b'').decode()
        token = self._extract_token_from_query(query_string)

        if token:
            self.user = await self.authenticate_token(token)

        # Accept connection (will authenticate on first message if not authenticated yet)
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        logger.info(f"WebSocket connected: upload_id={self.upload_id}, user={self.user}")

        # If authenticated, verify access and send current status
        if self.user:
            has_access = await self.verify_upload_access(self.upload_id, self.user)
            if not has_access:
                await self.send_error("Access denied to this upload")
                await self.close(code=4003)
                return

            # Send current upload status
            await self.send_current_status()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        logger.info(f"WebSocket disconnected: upload_id={self.upload_id}, code={close_code}")

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle messages from WebSocket client."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            # Handle authentication message
            if message_type == 'authenticate':
                token = data.get('token')
                if not token:
                    await self.send_error("Token required for authentication")
                    await self.close(code=4001)
                    return

                self.user = await self.authenticate_token(token)
                if not self.user:
                    await self.send_error("Invalid or expired token")
                    await self.close(code=4001)
                    return

                # Verify upload access
                has_access = await self.verify_upload_access(self.upload_id, self.user)
                if not has_access:
                    await self.send_error("Access denied to this upload")
                    await self.close(code=4003)
                    return

                await self.send(text_data=json.dumps({
                    'type': 'authenticated',
                    'message': 'Authentication successful'
                }))

                # Send current status
                await self.send_current_status()

            # Handle ping message
            elif message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }))

            else:
                logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}", exc_info=True)
            await self.send_error(f"Error processing message: {str(e)}")

    # Receive message from room group
    async def upload_progress(self, event):
        """Send progress update to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'progress',
            'percent': event['percent'],
            'message': event['message'],
            'current': event.get('current'),
            'total': event.get('total'),
        }))

    async def upload_status(self, event):
        """Send status update to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'status',
            'status': event['status'],
            'message': event['message'],
        }))

    async def upload_error(self, event):
        """Send error notification to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': event['message'],
            'details': event.get('details', ''),
        }))

    async def upload_complete(self, event):
        """Send completion notification to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'complete',
            'message': event['message'],
            'results': event.get('results', {}),
        }))

    # Helper methods
    async def send_error(self, message, details=''):
        """Send error message to client."""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'details': details,
        }))

    async def send_current_status(self):
        """Send current upload status to client."""
        try:
            upload = await self.get_upload(self.upload_id)
            if not upload:
                await self.send_error("Upload not found")
                return

            await self.send(text_data=json.dumps({
                'type': 'status',
                'status': upload.status,
                'message': self._get_status_message(upload.status),
                'progress': upload.progress_percent,
                'rows_processed': upload.rows_processed,
                'total_rows': upload.total_rows,
            }))
        except Exception as e:
            logger.error(f"Error sending current status: {e}", exc_info=True)

    def _extract_token_from_query(self, query_string):
        """Extract JWT token from query string."""
        if not query_string:
            return None

        params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
        return params.get('token')

    def _get_status_message(self, status):
        """Get human-readable message for upload status."""
        messages = {
            'pending': 'Upload queued for processing',
            'validating': 'Validating CSV file',
            'processing': 'Processing data through GabeDA',
            'completed': 'Upload processing complete',
            'failed': 'Upload processing failed',
            'cancelled': 'Upload cancelled by user',
        }
        return messages.get(status, f'Upload status: {status}')

    @database_sync_to_async
    def authenticate_token(self, token):
        """Authenticate user from JWT token."""
        try:
            from rest_framework_simplejwt.tokens import AccessToken

            access_token = AccessToken(token)
            user_id = access_token['user_id']
            user = User.objects.get(id=user_id)
            return user
        except Exception as e:
            logger.warning(f"Token authentication failed: {e}")
            return None

    @database_sync_to_async
    def verify_upload_access(self, upload_id, user):
        """Verify user has access to the upload."""
        try:
            upload = Upload.objects.select_related('company').get(id=upload_id)

            # Check if user has access to the company
            return upload.company.usercompany_set.filter(
                user=user,
                is_active=True
            ).exists()
        except ObjectDoesNotExist:
            return False

    @database_sync_to_async
    def get_upload(self, upload_id):
        """Get upload object from database."""
        try:
            return Upload.objects.get(id=upload_id)
        except ObjectDoesNotExist:
            return None


# Helper function to send progress from Celery tasks
def send_progress_update(upload_id, percent, message, current=None, total=None):
    """
    Send progress update from Celery task to WebSocket clients.

    Args:
        upload_id: Upload ID
        percent: Progress percentage (0-100)
        message: Progress message
        current: Current item count (optional)
        total: Total item count (optional)
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    channel_layer = get_channel_layer()
    room_group_name = f'upload_{upload_id}'

    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'upload_progress',
            'percent': percent,
            'message': message,
            'current': current,
            'total': total,
        }
    )


def send_status_update(upload_id, status, message):
    """
    Send status update from Celery task to WebSocket clients.

    Args:
        upload_id: Upload ID
        status: Upload status (pending, validating, processing, completed, failed)
        message: Status message
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    channel_layer = get_channel_layer()
    room_group_name = f'upload_{upload_id}'

    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'upload_status',
            'status': status,
            'message': message,
        }
    )


def send_error_notification(upload_id, message, details=''):
    """
    Send error notification from Celery task to WebSocket clients.

    Args:
        upload_id: Upload ID
        message: Error message
        details: Detailed error information (optional)
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    channel_layer = get_channel_layer()
    room_group_name = f'upload_{upload_id}'

    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'upload_error',
            'message': message,
            'details': details,
        }
    )


def send_completion_notification(upload_id, message, results=None):
    """
    Send completion notification from Celery task to WebSocket clients.

    Args:
        upload_id: Upload ID
        message: Completion message
        results: Processing results dict (optional)
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    channel_layer = get_channel_layer()
    room_group_name = f'upload_{upload_id}'

    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'upload_complete',
            'message': message,
            'results': results or {},
        }
    )
