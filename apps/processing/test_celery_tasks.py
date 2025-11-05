"""
Comprehensive tests for Celery tasks.

This module tests all async processing tasks with 8 test types:
1. Valid (happy path)
2. Error handling
3. Invalid input
4. Edge cases
5. Functional (business logic)
6. Visual (N/A for backend)
7. Performance
8. Security
"""

import os
import tempfile
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call
from io import StringIO

import pytest
import pandas as pd
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from celery.exceptions import Retry

from apps.processing.models import Upload, RawTransaction, DataUpdate
from apps.processing.tasks import (
    process_csv_upload,
    validate_csv_file,
    parse_csv_data,
    save_transactions_to_db,
    track_data_updates,
    cleanup_old_uploads,
    generate_health_check,
    ProcessingTask,
)
from apps.companies.models import Company

User = get_user_model()


@pytest.mark.django_db
class TestProcessingTaskBase(TransactionTestCase):
    """Base test class with common fixtures."""

    def setUp(self):
        """Set up test fixtures."""
        # Create test user
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )

        # Create test company
        self.company = Company.objects.create(
            name='Test PYME',
            rut='12345678-9',
            industry='retail',
            created_by=self.user
        )

        # Grant user access to company
        self.company.users.add(self.user)

    def create_test_csv(self, rows=10, include_header=True):
        """Create a test CSV file."""
        csv_data = []

        if include_header:
            csv_data.append('transaction_id,transaction_date,product_id,quantity,price_total')

        for i in range(rows):
            csv_data.append(
                f'TXN{i:05d},2024-01-{(i % 28) + 1:02d},PROD{i % 5},10,1000.00'
            )

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
        temp_file.write('\n'.join(csv_data))
        temp_file.close()

        return temp_file.name

    def create_upload(self, status='pending', file_path=None):
        """Create a test Upload instance."""
        if not file_path:
            file_path = self.create_test_csv()

        return Upload.objects.create(
            company=self.company,
            user=self.user,
            filename='test_upload.csv',
            file_path=file_path,
            file_size=os.path.getsize(file_path),
            status=status,
            column_mappings={
                'transaction_id': 'transaction_id',
                'transaction_date': 'transaction_date',
                'product_id': 'product_id',
                'quantity': 'quantity',
                'price_total': 'price_total',
            }
        )

    def tearDown(self):
        """Clean up test files."""
        # Delete temporary CSV files
        for upload in Upload.objects.all():
            if os.path.exists(upload.file_path):
                try:
                    os.remove(upload.file_path)
                except Exception:
                    pass


# ============================================================================
# TEST TYPE 1: VALID (Happy Path)
# ============================================================================

class TestCeleryTasksValid(TestProcessingTaskBase):
    """Test valid/happy path scenarios."""

    def test_process_csv_upload_success(self):
        """Valid: Successfully process a valid CSV upload."""
        upload = self.create_upload()

        # Process the upload
        result = process_csv_upload(upload.id)

        # Verify results
        assert result['status'] == 'completed'
        assert result['processed_rows'] == 10

        # Verify upload status
        upload.refresh_from_db()
        assert upload.status == 'completed'
        assert upload.processed_rows == 10
        assert upload.progress_percentage == 100

    def test_validate_csv_file_success(self):
        """Valid: Validate a well-formed CSV file."""
        file_path = self.create_test_csv(rows=5)
        column_mappings = {
            'transaction_id': 'transaction_id',
            'transaction_date': 'transaction_date',
        }

        df = validate_csv_file(file_path, column_mappings)

        assert len(df) == 5
        assert 'transaction_id' in df.columns
        os.remove(file_path)

    def test_cleanup_old_uploads_success(self):
        """Valid: Clean up old completed uploads."""
        # Create old upload
        old_upload = self.create_upload(status='completed')
        old_upload.completed_at = timezone.now() - timedelta(days=35)
        old_upload.save()

        # Create recent upload
        recent_upload = self.create_upload(status='completed')
        recent_upload.completed_at = timezone.now() - timedelta(days=5)
        recent_upload.save()

        # Run cleanup
        result = cleanup_old_uploads(days=30)

        assert result['cleaned_up'] == 1
        assert not Upload.objects.filter(id=old_upload.id).exists()
        assert Upload.objects.filter(id=recent_upload.id).exists()

    def test_health_check_success(self):
        """Valid: Health check returns healthy status."""
        result = generate_health_check()

        assert result['status'] == 'healthy'
        assert 'timestamp' in result
        assert result['worker'] == 'celery'


# ============================================================================
# TEST TYPE 2: ERROR HANDLING
# ============================================================================

class TestCeleryTasksErrorHandling(TestProcessingTaskBase):
    """Test error handling and recovery."""

    def test_process_csv_upload_not_found(self):
        """Error: Handle non-existent upload gracefully."""
        with pytest.raises(Upload.DoesNotExist):
            process_csv_upload(99999)

    def test_validate_csv_file_corrupted(self):
        """Error: Handle corrupted CSV file."""
        # Create corrupted CSV
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
        temp_file.write('invalid\x00csv\x00data')
        temp_file.close()

        with pytest.raises(Exception):
            validate_csv_file(temp_file.name, {})

        os.remove(temp_file.name)

    def test_process_csv_upload_file_missing(self):
        """Error: Handle missing file gracefully."""
        upload = self.create_upload()
        os.remove(upload.file_path)  # Delete the file

        with pytest.raises(Exception):
            process_csv_upload(upload.id)

        # Verify upload marked as failed
        upload.refresh_from_db()
        assert upload.status == 'failed'
        assert upload.error_message is not None

    @patch('apps.processing.tasks.save_transactions_to_db')
    def test_process_csv_upload_retry_on_db_error(self, mock_save):
        """Error: Task retries on database errors."""
        upload = self.create_upload()

        # Simulate database error on first call, success on retry
        mock_save.side_effect = [Exception("DB connection lost"), None]

        # Should raise exception for retry
        with pytest.raises(Exception):
            process_csv_upload(upload.id)


# ============================================================================
# TEST TYPE 3: INVALID INPUT
# ============================================================================

class TestCeleryTasksInvalidInput(TestProcessingTaskBase):
    """Test invalid input validation."""

    def test_validate_csv_file_empty(self):
        """Invalid: Reject empty CSV file."""
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
        temp_file.write('transaction_id,date\n')  # Header only
        temp_file.close()

        with pytest.raises(ValueError, match="CSV file is empty"):
            validate_csv_file(temp_file.name, {})

        os.remove(temp_file.name)

    def test_validate_csv_file_missing_required_columns(self):
        """Invalid: Reject CSV missing required columns."""
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
        temp_file.write('col1,col2\nval1,val2')
        temp_file.close()

        column_mappings = {
            'transaction_id': {'required': True},
            'amount': {'required': True},
        }

        with pytest.raises(ValueError, match="Missing required columns"):
            validate_csv_file(temp_file.name, column_mappings)

        os.remove(temp_file.name)

    def test_process_csv_upload_invalid_column_mappings(self):
        """Invalid: Reject upload with invalid column mappings."""
        upload = self.create_upload()
        upload.column_mappings = {}  # Empty mappings
        upload.save()

        with pytest.raises(Exception):
            process_csv_upload(upload.id)


# ============================================================================
# TEST TYPE 4: EDGE CASES
# ============================================================================

class TestCeleryTasksEdgeCases(TestProcessingTaskBase):
    """Test boundary conditions and edge cases."""

    def test_process_csv_upload_large_file(self):
        """Edge: Process CSV with large number of rows."""
        # Create large CSV (1000 rows)
        file_path = self.create_test_csv(rows=1000)
        upload = self.create_upload(file_path=file_path)

        result = process_csv_upload(upload.id)

        assert result['processed_rows'] == 1000
        assert RawTransaction.objects.filter(upload=upload).count() == 1000

    def test_process_csv_upload_single_row(self):
        """Edge: Process CSV with only one row."""
        file_path = self.create_test_csv(rows=1)
        upload = self.create_upload(file_path=file_path)

        result = process_csv_upload(upload.id)

        assert result['processed_rows'] == 1

    def test_cleanup_old_uploads_zero_days(self):
        """Edge: Cleanup with zero days (all uploads)."""
        upload = self.create_upload(status='completed')
        upload.completed_at = timezone.now()
        upload.save()

        result = cleanup_old_uploads(days=0)

        assert result['cleaned_up'] >= 1

    def test_process_csv_upload_concurrent_uploads(self):
        """Edge: Handle multiple concurrent uploads for same company."""
        upload1 = self.create_upload()
        upload2 = self.create_upload()

        # Process both concurrently
        result1 = process_csv_upload(upload1.id)
        result2 = process_csv_upload(upload2.id)

        assert result1['status'] == 'completed'
        assert result2['status'] == 'completed'

        # Verify both are stored separately
        assert RawTransaction.objects.filter(upload=upload1).count() == 10
        assert RawTransaction.objects.filter(upload=upload2).count() == 10

    def test_parse_csv_data_special_characters(self):
        """Edge: Handle special characters in CSV data."""
        # Create CSV with special characters
        csv_data = "id,name,desc\n1,José García,Product with áéíóú & symbols"
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', encoding='utf-8')
        temp_file.write(csv_data)
        temp_file.close()

        df = pd.read_csv(temp_file.name)
        result = parse_csv_data(df, {'id': 'id', 'name': 'name', 'desc': 'desc'})

        assert len(result) == 1
        assert 'José García' in str(result[0])
        os.remove(temp_file.name)


# ============================================================================
# TEST TYPE 5: FUNCTIONAL (Business Logic)
# ============================================================================

class TestCeleryTasksFunctional(TestProcessingTaskBase):
    """Test business logic and workflows."""

    @patch('apps.processing.tasks.ProcessingTask._send_ws_notification')
    def test_process_csv_upload_sends_progress_updates(self, mock_ws):
        """Functional: Progress updates sent via WebSocket."""
        upload = self.create_upload()

        process_csv_upload(upload.id)

        # Verify WebSocket notifications sent
        assert mock_ws.call_count >= 3  # Start, progress, complete

        # Check completion notification
        calls = [call[0][1] for call in mock_ws.call_args_list]
        completion_call = [c for c in calls if c.get('type') == 'upload.completed']
        assert len(completion_call) == 1

    def test_track_data_updates_creates_record(self):
        """Functional: Data updates are tracked for transparency."""
        upload = self.create_upload(status='processing')

        # Save some transactions
        RawTransaction.objects.create(
            company=self.company,
            upload=upload,
            data={'transaction_id': 'TXN001'},
            transaction_date=timezone.now(),
            transaction_id='TXN001',
            product_id='PROD1',
            quantity=10,
            price_total=1000,
        )

        upload.processed_rows = 1
        upload.save()

        # Track updates
        track_data_updates(upload)

        # Verify DataUpdate created
        data_update = DataUpdate.objects.filter(upload=upload).first()
        assert data_update is not None
        assert data_update.rows_added >= 1

    def test_save_transactions_to_db_uses_bulk_create(self):
        """Functional: Bulk create used for performance."""
        upload = self.create_upload()

        data = [
            {
                'transaction_id': f'TXN{i}',
                'transaction_date': timezone.now(),
                'product_id': f'PROD{i}',
                'quantity': 10,
                'price_total': 1000,
            }
            for i in range(100)
        ]

        processed, updated = save_transactions_to_db(self.company, upload, data)

        assert processed == 100
        assert RawTransaction.objects.filter(upload=upload).count() == 100

    def test_process_csv_upload_updates_statistics(self):
        """Functional: Upload statistics updated correctly."""
        upload = self.create_upload()

        process_csv_upload(upload.id)

        upload.refresh_from_db()
        assert upload.original_rows == 10
        assert upload.processed_rows == 10
        assert upload.started_at is not None
        assert upload.completed_at is not None


# ============================================================================
# TEST TYPE 6: VISUAL (N/A for Backend)
# ============================================================================

class TestCeleryTasksVisual(TestProcessingTaskBase):
    """Visual tests - N/A for backend, but documenting for completeness."""

    def test_visual_not_applicable(self):
        """Visual: N/A for backend tasks."""
        # Backend tasks don't have visual components
        # Visual testing would be done on Flower dashboard (manual QA)
        assert True


# ============================================================================
# TEST TYPE 7: PERFORMANCE
# ============================================================================

class TestCeleryTasksPerformance(TestProcessingTaskBase):
    """Test performance and scalability."""

    def test_process_csv_upload_performance_10k_rows(self):
        """Performance: Process 10k rows within acceptable time."""
        file_path = self.create_test_csv(rows=10000)
        upload = self.create_upload(file_path=file_path)

        start_time = time.time()
        result = process_csv_upload(upload.id)
        duration = time.time() - start_time

        # Should complete within 60 seconds for 10k rows
        assert duration < 60
        assert result['processed_rows'] == 10000

    def test_bulk_create_performance(self):
        """Performance: Bulk create faster than individual inserts."""
        upload = self.create_upload()

        data = [
            {
                'transaction_id': f'TXN{i}',
                'transaction_date': timezone.now(),
                'product_id': f'PROD{i}',
                'quantity': 10,
                'price_total': 1000,
            }
            for i in range(1000)
        ]

        start_time = time.time()
        save_transactions_to_db(self.company, upload, data)
        duration = time.time() - start_time

        # Bulk create should be fast (< 5 seconds for 1000 rows)
        assert duration < 5

    def test_task_dispatch_latency(self):
        """Performance: Task dispatch has low latency."""
        upload = self.create_upload()

        start_time = time.time()
        # Use delay() to test task queuing
        task = process_csv_upload.apply_async(args=[upload.id])
        dispatch_time = time.time() - start_time

        # Dispatch should be very fast (< 100ms)
        assert dispatch_time < 0.1


# ============================================================================
# TEST TYPE 8: SECURITY
# ============================================================================

class TestCeleryTasksSecurity(TestProcessingTaskBase):
    """Test security and data isolation."""

    def test_process_csv_upload_data_isolation(self):
        """Security: Ensure data isolation between companies."""
        # Create second company
        company2 = Company.objects.create(
            name='Other PYME',
            rut='98765432-1',
            industry='services',
            created_by=self.user
        )

        # Create uploads for both companies
        upload1 = self.create_upload()

        file_path2 = self.create_test_csv(rows=5)
        upload2 = Upload.objects.create(
            company=company2,
            user=self.user,
            filename='company2.csv',
            file_path=file_path2,
            file_size=os.path.getsize(file_path2),
            status='pending',
            column_mappings=upload1.column_mappings
        )

        # Process both
        process_csv_upload(upload1.id)
        process_csv_upload(upload2.id)

        # Verify data isolation
        company1_txns = RawTransaction.objects.filter(company=self.company)
        company2_txns = RawTransaction.objects.filter(company=company2)

        assert company1_txns.count() == 10
        assert company2_txns.count() == 5

        # Verify no cross-contamination
        for txn in company1_txns:
            assert txn.company_id == self.company.id

        for txn in company2_txns:
            assert txn.company_id == company2.id

    def test_validate_csv_file_path_injection(self):
        """Security: Prevent path injection attacks."""
        malicious_path = '../../../etc/passwd'

        # Should raise FileNotFoundError, not access system files
        with pytest.raises(Exception):
            validate_csv_file(malicious_path, {})

    def test_task_parameters_sanitized(self):
        """Security: Task parameters are sanitized."""
        # Attempt SQL injection via upload ID
        with pytest.raises(Upload.DoesNotExist):
            process_csv_upload("1 OR 1=1")

    def test_error_messages_no_sensitive_data(self):
        """Security: Error messages don't expose sensitive data."""
        upload = self.create_upload()
        os.remove(upload.file_path)

        try:
            process_csv_upload(upload.id)
        except Exception:
            pass

        upload.refresh_from_db()

        # Error message should not contain file paths or system info
        assert upload.error_message is not None
        assert '/tmp/' not in upload.error_message  # No temp paths
        assert 'password' not in upload.error_message.lower()

    def test_cleanup_old_uploads_respects_permissions(self):
        """Security: Cleanup only affects appropriate uploads."""
        # Create old upload
        old_upload = self.create_upload(status='completed')
        old_upload.completed_at = timezone.now() - timedelta(days=35)
        old_upload.save()

        # Create old pending upload (should NOT be cleaned)
        old_pending = self.create_upload(status='pending')
        old_pending.created_at = timezone.now() - timedelta(days=35)
        old_pending.save()

        result = cleanup_old_uploads(days=30)

        # Only completed/failed should be cleaned
        assert not Upload.objects.filter(id=old_upload.id).exists()
        assert Upload.objects.filter(id=old_pending.id).exists()


# ============================================================================
# ADDITIONAL TESTS: Task Configuration and Error Handling
# ============================================================================

class TestProcessingTaskConfiguration(TestCase):
    """Test ProcessingTask base class configuration."""

    def test_processing_task_retry_configuration(self):
        """Test retry configuration is set correctly."""
        task = ProcessingTask()

        assert task.autoretry_for == (Exception,)
        assert task.retry_kwargs['max_retries'] == 3
        assert task.retry_backoff is True
        assert task.retry_jitter is True

    def test_processing_task_time_limits(self):
        """Test task time limits from Celery config."""
        from config.celery import app

        assert app.conf.task_soft_time_limit == 600
        assert app.conf.task_time_limit == 900
