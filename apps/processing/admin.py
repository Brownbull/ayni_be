"""
Django admin configuration for processing models.
"""

from django.contrib import admin
from .models import Upload, ColumnMapping, RawTransaction, DataUpdate


@admin.register(Upload)
class UploadAdmin(admin.ModelAdmin):
    """Admin interface for Upload model."""

    list_display = [
        'filename', 'company', 'user', 'status',
        'original_rows', 'processed_rows', 'progress_percentage',
        'created_at'
    ]
    list_filter = ['status', 'created_at', 'completed_at']
    search_fields = ['filename', 'company__name', 'user__email']
    readonly_fields = ['created_at', 'started_at', 'completed_at']
    ordering = ['-created_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'user', 'filename', 'file_path', 'file_size')
        }),
        ('Processing Status', {
            'fields': ('status', 'progress_percentage')
        }),
        ('Statistics', {
            'fields': ('original_rows', 'processed_rows', 'updated_rows', 'error_rows')
        }),
        ('Column Mappings', {
            'fields': ('column_mappings',),
            'classes': ('collapse',)
        }),
        ('Errors', {
            'fields': ('error_message', 'error_details'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ColumnMapping)
class ColumnMappingAdmin(admin.ModelAdmin):
    """Admin interface for ColumnMapping model."""

    list_display = ['mapping_name', 'company', 'is_default', 'created_at', 'updated_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['mapping_name', 'company__name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'mapping_name', 'is_default')
        }),
        ('Mappings', {
            'fields': ('mappings', 'formats', 'defaults')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(RawTransaction)
class RawTransactionAdmin(admin.ModelAdmin):
    """Admin interface for RawTransaction model."""

    list_display = [
        'transaction_id', 'company', 'transaction_date',
        'product_id', 'quantity', 'price_total', 'processed_at'
    ]
    list_filter = ['transaction_date', 'processed_at', 'company']
    search_fields = ['transaction_id', 'product_id', 'customer_id', 'company__name']
    readonly_fields = ['processed_at']
    ordering = ['-transaction_date']

    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'upload')
        }),
        ('Denormalized Fields', {
            'fields': (
                'transaction_date', 'transaction_id', 'product_id',
                'customer_id', 'category', 'quantity', 'price_total', 'cost_total'
            )
        }),
        ('Full Data (JSON)', {
            'fields': ('data',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('processed_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(DataUpdate)
class DataUpdateAdmin(admin.ModelAdmin):
    """Admin interface for DataUpdate model."""

    list_display = [
        'company', 'period', 'period_type',
        'rows_before', 'rows_after', 'net_change',
        'timestamp'
    ]
    list_filter = ['period_type', 'timestamp']
    search_fields = ['company__name', 'period']
    readonly_fields = ['timestamp', 'net_change']
    ordering = ['-timestamp']

    def net_change(self, obj):
        """Display net change in admin."""
        return obj.net_change
    net_change.short_description = 'Net Change'

    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'upload', 'user')
        }),
        ('Period', {
            'fields': ('period', 'period_type')
        }),
        ('Statistics', {
            'fields': (
                'rows_before', 'rows_after',
                'rows_updated', 'rows_added', 'rows_deleted'
            )
        }),
        ('Changes Summary', {
            'fields': ('changes_summary',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('timestamp',),
            'classes': ('collapse',)
        }),
    )
