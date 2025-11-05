"""
Data processing models for AYNI platform.

This module defines models for CSV uploads, raw transactions,
column mappings, and data update tracking.
"""

from django.db import models
from django.utils import timezone
from django.conf import settings


class Upload(models.Model):
    """
    Tracks CSV file uploads and processing status.

    Attributes:
        company: Associated company
        user: User who uploaded the file
        filename: Original filename
        file_path: Path to stored file
        status: Processing status
        column_mappings: User-defined column mappings (JSON)
        original_rows: Number of rows in original file
        processed_rows: Number of rows successfully processed
        updated_rows: Number of rows that updated existing data
        error_message: Error details if processing failed
        created_at: Upload timestamp
        completed_at: Processing completion timestamp
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('validating', 'Validating'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='uploads'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploads'
    )

    # File information
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=512)
    file_size = models.BigIntegerField(help_text='File size in bytes')

    # Processing status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )

    # Column mappings (stores user's column name mappings)
    column_mappings = models.JSONField(
        default=dict,
        help_text='Maps user CSV columns to COLUMN_SCHEMA fields'
    )

    # Processing statistics
    original_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    updated_rows = models.IntegerField(default=0)
    error_rows = models.IntegerField(default=0)

    # Error tracking
    error_message = models.TextField(null=True, blank=True)
    error_details = models.JSONField(
        null=True,
        blank=True,
        help_text='Detailed error information by row'
    )

    # Progress tracking (0-100)
    progress_percentage = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'uploads'
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} - {self.company.name} ({self.status})"

    def mark_started(self):
        """Mark upload as started processing."""
        self.status = 'processing'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])

    def mark_completed(self):
        """Mark upload as successfully completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.progress_percentage = 100
        self.save(update_fields=['status', 'completed_at', 'progress_percentage'])

    def mark_failed(self, error_message):
        """Mark upload as failed with error message."""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'completed_at'])

    def update_progress(self, percentage):
        """Update processing progress."""
        self.progress_percentage = min(100, max(0, percentage))
        self.save(update_fields=['progress_percentage'])


class ColumnMapping(models.Model):
    """
    Saved column mappings for companies.

    Allows companies to save their column mapping configurations
    for reuse across multiple uploads.

    Attributes:
        company: Associated company
        mapping_name: User-friendly name for this mapping
        mappings: JSON object mapping CSV columns to schema columns
        formats: JSON object with date/number format specifications
        defaults: JSON object with default values for missing columns
        created_at: Creation timestamp
        updated_at: Last update timestamp
        is_default: Whether this is the default mapping for the company
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='column_mappings'
    )
    mapping_name = models.CharField(max_length=100)

    # Mapping configuration
    mappings = models.JSONField(
        help_text='Maps CSV column names to COLUMN_SCHEMA fields'
    )
    formats = models.JSONField(
        default=dict,
        help_text='Date and number format specifications per column'
    )
    defaults = models.JSONField(
        default=dict,
        help_text='Default values for missing optional columns'
    )

    # Metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = 'column_mappings'
        unique_together = ['company', 'mapping_name']
        indexes = [
            models.Index(fields=['company', 'is_default']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.mapping_name} - {self.company.name}"

    def save(self, *args, **kwargs):
        """Override save to ensure only one default mapping per company."""
        if self.is_default:
            # Remove default flag from other mappings for this company
            ColumnMapping.objects.filter(
                company=self.company,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class RawTransaction(models.Model):
    """
    Stores raw transactional data from uploaded CSVs.

    This model stores the processed data in COLUMN_SCHEMA format.
    Data is stored as JSONB for flexibility while maintaining schema validation.

    Attributes:
        company: Associated company (tenant isolation)
        upload: Associated upload batch
        data: Transaction data following COLUMN_SCHEMA
        processed_at: Processing timestamp
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='raw_transactions',
        db_index=True
    )
    upload = models.ForeignKey(
        Upload,
        on_delete=models.CASCADE,
        related_name='transactions',
        db_index=True
    )

    # Transaction data stored as JSON following COLUMN_SCHEMA
    data = models.JSONField(
        help_text='Transaction data following COLUMN_SCHEMA from src/core/constants.py'
    )

    # Computed fields for quick queries (denormalized)
    transaction_date = models.DateTimeField(db_index=True)
    transaction_id = models.CharField(max_length=255, db_index=True)
    product_id = models.CharField(max_length=255, db_index=True)
    customer_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    category = models.CharField(max_length=255, null=True, blank=True, db_index=True)

    # Financial fields (denormalized for quick queries)
    quantity = models.FloatField()
    price_total = models.FloatField()
    cost_total = models.FloatField(null=True, blank=True)

    processed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'raw_transactions'
        indexes = [
            models.Index(fields=['company', 'transaction_date']),
            models.Index(fields=['company', 'product_id']),
            models.Index(fields=['company', 'customer_id']),
            models.Index(fields=['company', 'category']),
            models.Index(fields=['transaction_date']),
            models.Index(fields=['upload']),
        ]
        ordering = ['-transaction_date']

    def __str__(self):
        return f"Transaction {self.transaction_id} - {self.company.name}"


class DataUpdate(models.Model):
    """
    Tracks data updates for transparency and audit purposes.

    Records how many rows were affected by each upload,
    providing users with clear feedback about data changes.

    Attributes:
        company: Associated company
        upload: Associated upload
        period: Time period affected (e.g., "2024-01", "2024-Q1")
        period_type: Type of period (daily, monthly, etc.)
        rows_before: Number of rows before update
        rows_after: Number of rows after update
        rows_updated: Number of rows modified
        rows_added: Number of new rows
        rows_deleted: Number of rows removed
        timestamp: Update timestamp
        user: User who performed the update
    """

    PERIOD_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='data_updates'
    )
    upload = models.ForeignKey(
        Upload,
        on_delete=models.CASCADE,
        related_name='data_updates'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='data_updates'
    )

    # Period information
    period = models.CharField(max_length=50)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)

    # Update statistics
    rows_before = models.IntegerField(default=0)
    rows_after = models.IntegerField(default=0)
    rows_updated = models.IntegerField(default=0)
    rows_added = models.IntegerField(default=0)
    rows_deleted = models.IntegerField(default=0)

    # Additional metadata
    changes_summary = models.JSONField(
        default=dict,
        help_text='Detailed summary of changes by aggregation level'
    )

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'data_updates'
        indexes = [
            models.Index(fields=['company', 'period_type']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['upload']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.company.name} - {self.period} ({self.period_type})"

    @property
    def net_change(self):
        """Calculate net change in rows."""
        return self.rows_added - self.rows_deleted
