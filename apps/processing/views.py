"""
Views for data processing and upload management.
"""

import os
import csv
import io
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Upload, ColumnMapping, RawTransaction, DataUpdate
from .serializers import (
    UploadSerializer,
    UploadCreateSerializer,
    ColumnMappingSerializer,
    RawTransactionSerializer,
    DataUpdateSerializer,
)
from apps.companies.models import UserCompany


class UploadViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing CSV uploads.

    Endpoints:
    - GET /api/processing/uploads/ - List all uploads for user's companies
    - POST /api/processing/uploads/ - Create new upload
    - GET /api/processing/uploads/{id}/ - Get upload details
    - DELETE /api/processing/uploads/{id}/ - Cancel/delete upload
    - GET /api/processing/uploads/{id}/progress/ - Get upload progress
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UploadSerializer

    def get_queryset(self):
        """
        Return uploads for companies user has access to.
        """
        user = self.request.user

        # Get all companies user has access to
        user_companies = UserCompany.objects.filter(
            user=user
        ).values_list('company_id', flat=True)

        return Upload.objects.filter(
            company_id__in=user_companies
        ).select_related('company', 'user')

    def create(self, request, *args, **kwargs):
        """
        Create new CSV upload.

        Process:
        1. Validate file and mappings
        2. Save file to storage
        3. Create upload record
        4. Trigger async processing (future: Celery task)
        5. Return upload ID and status
        """
        serializer = UploadCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        uploaded_file = validated_data['file']
        company_id = validated_data['company']
        column_mappings = validated_data['column_mappings']

        # BUSINESS RULE: One upload per company at a time
        # This prevents resource exhaustion and ensures fair processing
        # Maximum concurrent uploads = number of unique registered companies
        if Upload.has_active_upload(company_id):
            active_upload = Upload.get_active_upload(company_id)
            return Response(
                {
                    'error': 'Upload already in progress',
                    'detail': 'This company already has an upload being processed. '
                              'Please wait for it to complete before uploading another file.',
                    'active_upload_id': active_upload.id,
                    'active_upload_status': active_upload.status,
                    'active_upload_progress': active_upload.progress_percentage,
                    'active_upload_filename': active_upload.filename,
                },
                status=status.HTTP_409_CONFLICT
            )

        try:
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            original_name = uploaded_file.name
            safe_name = "".join(c for c in original_name if c.isalnum() or c in '._- ')
            filename = f"{timestamp}_{request.user.id}_{safe_name}"

            # Save file to storage
            upload_path = f"uploads/{company_id}/{filename}"
            file_path = default_storage.save(upload_path, uploaded_file)

            # Create upload record
            upload = Upload.objects.create(
                company_id=company_id,
                user=request.user,
                filename=original_name,
                file_path=file_path,
                file_size=uploaded_file.size,
                column_mappings=column_mappings,
                status='pending',
            )

            # Perform initial validation
            try:
                row_count = self._validate_csv_file(file_path)
                upload.original_rows = row_count
                upload.status = 'validating'
                upload.save(update_fields=['original_rows', 'status'])
            except Exception as e:
                upload.mark_failed(f"CSV validation failed: {str(e)}")
                return Response(
                    {
                        'error': 'CSV validation failed',
                        'detail': str(e),
                        'upload_id': upload.id
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # TODO: Trigger Celery task for async processing (Task 008)
            # from .tasks import process_upload_task
            # process_upload_task.delay(upload.id)

            # Return upload details
            output_serializer = UploadSerializer(upload)
            return Response(
                output_serializer.data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {
                    'error': 'Upload failed',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _validate_csv_file(self, file_path):
        """
        Validate CSV file structure and count rows.

        Returns:
            int: Number of data rows (excluding header)

        Raises:
            ValueError: If CSV is invalid
        """
        full_path = default_storage.path(file_path)

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                # Read first few bytes to detect format
                sample = f.read(1024)
                f.seek(0)

                # Try to detect dialect
                try:
                    dialect = csv.Sniffer().sniff(sample)
                except csv.Error:
                    dialect = csv.excel

                # Count rows
                reader = csv.reader(f, dialect=dialect)

                # Read header
                try:
                    header = next(reader)
                except StopIteration:
                    raise ValueError("CSV file is empty")

                if not header or len(header) == 0:
                    raise ValueError("CSV file has no columns")

                # Count data rows
                row_count = sum(1 for row in reader if row)

                if row_count == 0:
                    raise ValueError("CSV file has no data rows")

                return row_count

        except UnicodeDecodeError:
            raise ValueError("CSV file encoding is invalid. Please use UTF-8.")
        except Exception as e:
            raise ValueError(f"Failed to read CSV file: {str(e)}")

    @action(detail=True, methods=['get'])
    def progress(self, request, pk=None):
        """
        Get upload progress.

        Returns:
            {
                "id": 123,
                "status": "processing",
                "progress_percentage": 45,
                "original_rows": 10000,
                "processed_rows": 4500
            }
        """
        upload = self.get_object()

        return Response({
            'id': upload.id,
            'status': upload.status,
            'progress_percentage': upload.progress_percentage,
            'original_rows': upload.original_rows,
            'processed_rows': upload.processed_rows,
            'updated_rows': upload.updated_rows,
            'error_rows': upload.error_rows,
            'error_message': upload.error_message,
            'created_at': upload.created_at,
            'started_at': upload.started_at,
            'completed_at': upload.completed_at,
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel a pending or processing upload.
        """
        upload = self.get_object()

        # Only allow cancellation of pending or processing uploads
        if upload.status not in ['pending', 'validating', 'processing']:
            return Response(
                {'error': f'Cannot cancel upload with status: {upload.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # TODO: Cancel Celery task if exists (Task 008)
        # from celery import current_app
        # current_app.control.revoke(upload.celery_task_id, terminate=True)

        upload.status = 'cancelled'
        upload.completed_at = timezone.now()
        upload.save(update_fields=['status', 'completed_at'])

        return Response({'status': 'cancelled'})

    def destroy(self, request, *args, **kwargs):
        """
        Delete an upload and its associated file.

        Only allowed for uploads that are completed, failed, or cancelled.
        """
        upload = self.get_object()

        # Prevent deletion of in-progress uploads
        if upload.status in ['pending', 'validating', 'processing']:
            return Response(
                {'error': 'Cannot delete upload that is still processing. Cancel it first.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user has delete permission
        user_company = UserCompany.objects.filter(
            user=request.user,
            company=upload.company
        ).first()

        if not user_company or not user_company.can_delete_data:
            return Response(
                {'error': 'You do not have permission to delete uploads for this company.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Delete file from storage
        if upload.file_path:
            try:
                if default_storage.exists(upload.file_path):
                    default_storage.delete(upload.file_path)
            except Exception as e:
                # Log error but continue with database deletion
                print(f"Failed to delete file {upload.file_path}: {e}")

        # Delete database record
        upload.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class ColumnMappingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing saved column mappings.

    Endpoints:
    - GET /api/processing/mappings/ - List mappings for user's companies
    - POST /api/processing/mappings/ - Create new mapping
    - GET /api/processing/mappings/{id}/ - Get mapping details
    - PATCH /api/processing/mappings/{id}/ - Update mapping
    - DELETE /api/processing/mappings/{id}/ - Delete mapping
    - GET /api/processing/mappings/company/{company_id}/ - Get company's default mapping
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ColumnMappingSerializer

    def get_queryset(self):
        """Return mappings for companies user has access to."""
        user = self.request.user

        user_companies = UserCompany.objects.filter(
            user=user
        ).values_list('company_id', flat=True)

        return ColumnMapping.objects.filter(
            company_id__in=user_companies
        ).select_related('company')

    def perform_create(self, serializer):
        """Validate user has permission for company before creating."""
        company_id = serializer.validated_data['company'].id

        user_company = UserCompany.objects.filter(
            user=self.request.user,
            company_id=company_id
        ).first()

        if not user_company:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have access to this company.")

        serializer.save()

    @action(detail=False, methods=['get'], url_path='company/(?P<company_id>[^/.]+)')
    def by_company(self, request, company_id=None):
        """
        Get default column mapping for a company.

        Returns the company's default mapping if exists,
        otherwise returns None.
        """
        # Verify user has access to company
        user_company = UserCompany.objects.filter(
            user=request.user,
            company_id=company_id
        ).first()

        if not user_company:
            return Response(
                {'error': 'You do not have access to this company.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get default mapping
        mapping = ColumnMapping.objects.filter(
            company_id=company_id,
            is_default=True
        ).first()

        if mapping:
            serializer = self.get_serializer(mapping)
            return Response(serializer.data)
        else:
            return Response({'mapping': None})


class RawTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing raw transaction data.

    Read-only endpoint for viewing processed transactions.

    Endpoints:
    - GET /api/processing/transactions/ - List transactions for user's companies
    - GET /api/processing/transactions/{id}/ - Get transaction details
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RawTransactionSerializer

    def get_queryset(self):
        """Return transactions for companies user has access to."""
        user = self.request.user

        user_companies = UserCompany.objects.filter(
            user=user
        ).values_list('company_id', flat=True)

        queryset = RawTransaction.objects.filter(
            company_id__in=user_companies
        ).select_related('company', 'upload')

        # Optional filters
        company_id = self.request.query_params.get('company')
        upload_id = self.request.query_params.get('upload')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        if company_id:
            queryset = queryset.filter(company_id=company_id)
        if upload_id:
            queryset = queryset.filter(upload_id=upload_id)
        if start_date:
            queryset = queryset.filter(transaction_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(transaction_date__lte=end_date)

        return queryset[:1000]  # Limit to 1000 records for performance


class DataUpdateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing data update tracking records.

    Read-only endpoint for audit trail of data modifications.

    Endpoints:
    - GET /api/processing/updates/ - List data updates for user's companies
    - GET /api/processing/updates/{id}/ - Get update details
    """

    permission_classes = [IsAuthenticated]
    serializer_class = DataUpdateSerializer

    def get_queryset(self):
        """Return data updates for companies user has access to."""
        user = self.request.user

        user_companies = UserCompany.objects.filter(
            user=user
        ).values_list('company_id', flat=True)

        queryset = DataUpdate.objects.filter(
            company_id__in=user_companies
        ).select_related('company', 'upload', 'user')

        # Optional filters
        company_id = self.request.query_params.get('company')
        upload_id = self.request.query_params.get('upload')

        if company_id:
            queryset = queryset.filter(company_id=company_id)
        if upload_id:
            queryset = queryset.filter(upload_id=upload_id)

        return queryset
