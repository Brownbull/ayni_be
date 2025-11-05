"""
Celery tasks for async CSV processing.

This module contains asynchronous tasks for:
- CSV file validation and parsing
- Data processing through GabeDA engine
- Progress tracking and WebSocket notifications
- Error handling and retry logic
"""

import logging
import pandas as pd
from celery import shared_task, Task
from django.utils import timezone
from django.db import transaction as db_transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from apps.processing.models import Upload, RawTransaction, DataUpdate
from apps.companies.models import Company
from apps.processing.gabeda_wrapper import (
    GabedaWrapper,
    GabedaProcessingError,
    GabedaValidationError,
    process_upload_with_gabeda
)

logger = logging.getLogger(__name__)


class ProcessingTask(Task):
    """
    Base task class with error handling and retry logic.

    This class provides common functionality for all processing tasks:
    - Automatic retry on failure
    - Progress tracking
    - WebSocket notifications
    - Error logging
    """

    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 5}
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes
    retry_jitter = True  # Add randomness to retry timing

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Called when task fails after all retries.

        Args:
            exc: The exception raised
            task_id: Unique task ID
            args: Task arguments
            kwargs: Task keyword arguments
            einfo: Exception info
        """
        logger.error(
            f"Task {task_id} failed permanently: {exc}",
            exc_info=einfo,
            extra={'task_id': task_id, 'args': args, 'kwargs': kwargs}
        )

        # Update upload status if upload_id provided
        upload_id = kwargs.get('upload_id') or (args[0] if args else None)
        if upload_id:
            try:
                upload = Upload.objects.get(id=upload_id)
                upload.mark_failed(str(exc))

                # Send WebSocket notification
                self._send_ws_notification(upload.id, {
                    'type': 'upload.failed',
                    'upload_id': upload.id,
                    'error': str(exc),
                })
            except Upload.DoesNotExist:
                logger.error(f"Upload {upload_id} not found for failure handling")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """
        Called when task is retried.

        Args:
            exc: The exception that caused retry
            task_id: Unique task ID
            args: Task arguments
            kwargs: Task keyword arguments
            einfo: Exception info
        """
        logger.warning(
            f"Task {task_id} retrying: {exc}",
            extra={'task_id': task_id, 'retry': self.request.retries}
        )

    def _send_ws_notification(self, upload_id, message):
        """
        Send WebSocket notification to frontend.

        Args:
            upload_id: Upload ID for channel routing
            message: Message dict to send
        """
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"upload_{upload_id}",
                message
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {e}")

    def update_progress(self, upload_id, percentage, message=None):
        """
        Update upload progress and send WebSocket notification.

        Args:
            upload_id: Upload ID
            percentage: Progress percentage (0-100)
            message: Optional status message
        """
        try:
            upload = Upload.objects.get(id=upload_id)
            upload.update_progress(percentage)

            # Send WebSocket notification
            self._send_ws_notification(upload_id, {
                'type': 'upload.progress',
                'upload_id': upload_id,
                'progress': percentage,
                'message': message or f"Processing: {percentage}%",
            })
        except Upload.DoesNotExist:
            logger.error(f"Upload {upload_id} not found for progress update")


@shared_task(base=ProcessingTask, bind=True, name='apps.processing.tasks.process_csv_upload')
def process_csv_upload(self, upload_id):
    """
    Main task to process uploaded CSV file through GabeDA engine.

    This task orchestrates the entire CSV processing pipeline:
    1. Validate CSV file format and structure
    2. Preprocess data with GabeDA
    3. Execute GabeDA feature engine
    4. Save multi-level aggregations to database
    5. Track data updates for transparency
    6. Send completion notification

    Args:
        upload_id: ID of Upload model instance

    Returns:
        dict: Processing results with statistics

    Raises:
        Upload.DoesNotExist: If upload not found
        GabedaValidationError: If CSV validation fails
        GabedaProcessingError: If processing fails
        Exception: For other errors
    """
    logger.info(f"Starting GabeDA processing for upload {upload_id}")

    try:
        # Get upload instance
        upload = Upload.objects.select_related('company', 'uploaded_by').get(id=upload_id)

        # Mark as started
        upload.mark_started()
        self.update_progress(upload_id, 0, "Starting GabeDA processing...")

        # Step 1: Load and validate CSV (10-20%)
        logger.info(f"Loading CSV file: {upload.filename}")
        self.update_progress(upload_id, 10, "Loading and validating CSV...")

        wrapper = GabedaWrapper(upload)
        df = wrapper.load_and_validate_csv()
        upload.original_rows = len(df)
        upload.save(update_fields=['original_rows'])

        # Step 2: Preprocess data (20-40%)
        logger.info(f"Preprocessing {len(df)} rows")
        self.update_progress(upload_id, 30, f"Preprocessing {len(df)} rows...")

        df_processed = wrapper.preprocess_data()

        # Step 3: Execute GabeDA engine (40-70%)
        logger.info(f"Executing GabeDA feature engine")
        self.update_progress(upload_id, 50, "Calculating features...")

        # For MVP, we skip full GabeDA execution and go straight to aggregations
        # Full GabeDA integration will be in future iterations
        # gabeda_results = wrapper.execute_gabeda_engine()

        # Step 4: Persist to database (70-90%)
        logger.info(f"Persisting results to database")
        self.update_progress(upload_id, 70, "Saving aggregations...")

        db_counts = wrapper.persist_to_database()

        upload.processed_rows = db_counts['raw_transactions']
        upload.updated_rows = db_counts['raw_transactions']
        upload.save(update_fields=['processed_rows', 'updated_rows'])

        # Step 5: Finalize (90-100%)
        logger.info(f"Finalizing processing")
        self.update_progress(upload_id, 95, "Finalizing...")

        # Mark as completed
        upload.mark_completed()
        self.update_progress(upload_id, 100, "Processing complete!")

        # Send success notification
        self._send_ws_notification(upload_id, {
            'type': 'upload.completed',
            'upload_id': upload_id,
            'processed_rows': upload.processed_rows,
            'updated_rows': upload.updated_rows,
            'data_quality_score': wrapper.data_quality_score,
            'aggregation_counts': db_counts,
        })

        logger.info(
            f"Successfully processed upload {upload_id}: "
            f"{upload.processed_rows} rows, "
            f"quality score: {wrapper.data_quality_score:.1f}%"
        )

        return {
            'upload_id': upload_id,
            'status': 'completed',
            'original_rows': upload.original_rows,
            'processed_rows': upload.processed_rows,
            'updated_rows': upload.updated_rows,
            'data_quality_score': wrapper.data_quality_score,
            'aggregation_counts': db_counts,
        }

    except Upload.DoesNotExist:
        logger.error(f"Upload {upload_id} not found")
        raise

    except GabedaValidationError as e:
        logger.error(f"Validation error for upload {upload_id}: {e}")
        # Re-raise to trigger retry (validation errors may be transient)
        raise

    except GabedaProcessingError as e:
        logger.error(f"Processing error for upload {upload_id}: {e}")
        # Re-raise to trigger retry
        raise

    except Exception as e:
        logger.error(f"Unexpected error processing upload {upload_id}: {e}", exc_info=True)
        # Re-raise to trigger retry
        raise


def validate_csv_file(file_path, column_mappings):
    """
    Validate CSV file format and structure.

    Args:
        file_path: Path to CSV file
        column_mappings: Column mapping configuration

    Returns:
        pandas.DataFrame: Validated dataframe

    Raises:
        ValidationError: If validation fails
    """
    try:
        # Read CSV file
        df = pd.read_csv(file_path)

        # Check if file is empty
        if df.empty:
            raise ValueError("CSV file is empty")

        # Validate required columns from mappings
        required_columns = [
            col for col, schema_field in column_mappings.items()
            if schema_field.get('required', False)
        ]

        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

        logger.info(f"CSV validation passed: {len(df)} rows, {len(df.columns)} columns")
        return df

    except pd.errors.EmptyDataError:
        raise ValueError("CSV file is empty or corrupted")

    except Exception as e:
        logger.error(f"CSV validation error: {e}")
        raise


def parse_csv_data(df, column_mappings):
    """
    Parse CSV data using column mappings.

    Transforms CSV columns to COLUMN_SCHEMA format.

    Args:
        df: pandas DataFrame
        column_mappings: Column mapping configuration

    Returns:
        list: List of parsed transaction dicts
    """
    parsed_data = []

    for idx, row in df.iterrows():
        try:
            # Transform row using column mappings
            transaction = {}
            for csv_col, schema_field in column_mappings.items():
                if csv_col in row:
                    value = row[csv_col]
                    # Apply any transformations
                    # TODO: Add date parsing, number formatting, etc.
                    transaction[schema_field] = value

            parsed_data.append(transaction)

        except Exception as e:
            logger.warning(f"Error parsing row {idx}: {e}")
            # Skip invalid rows but continue processing
            continue

    logger.info(f"Parsed {len(parsed_data)} transactions from CSV")
    return parsed_data


def save_transactions_to_db(company, upload, data):
    """
    Save parsed transactions to database.

    Uses bulk_create for performance with large datasets.

    Args:
        company: Company instance
        upload: Upload instance
        data: List of transaction dicts

    Returns:
        tuple: (processed_rows, updated_rows)
    """
    transactions = []

    with db_transaction.atomic():
        for transaction_data in data:
            # Extract denormalized fields for indexing
            transaction = RawTransaction(
                company=company,
                upload=upload,
                data=transaction_data,
                transaction_date=transaction_data.get('transaction_date'),
                transaction_id=transaction_data.get('transaction_id'),
                product_id=transaction_data.get('product_id'),
                customer_id=transaction_data.get('customer_id'),
                category=transaction_data.get('category'),
                quantity=transaction_data.get('quantity', 0),
                price_total=transaction_data.get('price_total', 0),
                cost_total=transaction_data.get('cost_total'),
            )
            transactions.append(transaction)

        # Bulk create for performance
        RawTransaction.objects.bulk_create(transactions, batch_size=1000)

    logger.info(f"Saved {len(transactions)} transactions to database")

    return len(transactions), 0  # For now, all are new (no updates)


def track_data_updates(upload):
    """
    Track data updates for transparency.

    Creates DataUpdate records for affected periods.

    Args:
        upload: Upload instance
    """
    # TODO: Implement period detection and tracking
    # For now, create a simple monthly update record

    DataUpdate.objects.create(
        company=upload.company,
        upload=upload,
        user=upload.user,
        period="2024-01",  # TODO: Detect from transaction dates
        period_type="monthly",
        rows_before=0,
        rows_after=upload.processed_rows,
        rows_added=upload.processed_rows,
        rows_updated=0,
        rows_deleted=0,
    )

    logger.info(f"Created data update tracking for upload {upload.id}")


@shared_task(name='apps.processing.tasks.cleanup_old_uploads')
def cleanup_old_uploads(days=30):
    """
    Cleanup old completed/failed uploads.

    Removes uploads older than specified days to free up storage.

    Args:
        days: Number of days to retain (default: 30)

    Returns:
        dict: Cleanup statistics
    """
    from datetime import timedelta

    cutoff_date = timezone.now() - timedelta(days=days)

    # Find old uploads
    old_uploads = Upload.objects.filter(
        completed_at__lt=cutoff_date,
        status__in=['completed', 'failed']
    )

    count = old_uploads.count()
    logger.info(f"Cleaning up {count} uploads older than {days} days")

    # Delete uploads (CASCADE will delete related data)
    old_uploads.delete()

    return {
        'cleaned_up': count,
        'cutoff_date': cutoff_date.isoformat(),
    }


@shared_task(name='apps.processing.tasks.generate_health_check')
def generate_health_check():
    """
    Health check task for monitoring.

    Used by Flower and monitoring tools to verify Celery is running.

    Returns:
        dict: Health status
    """
    return {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'worker': 'celery',
    }
