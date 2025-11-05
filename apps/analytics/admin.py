"""
Django admin configuration for analytics models.
"""

from django.contrib import admin
from .models import (
    DailyAggregation, WeeklyAggregation, MonthlyAggregation,
    QuarterlyAggregation, YearlyAggregation,
    ProductAggregation, CustomerAggregation, CategoryAggregation,
    Benchmark
)


@admin.register(DailyAggregation)
class DailyAggregationAdmin(admin.ModelAdmin):
    """Admin interface for DailyAggregation model."""

    list_display = ['company', 'date', 'updated_at']
    list_filter = ['date', 'updated_at']
    search_fields = ['company__name']
    readonly_fields = ['updated_at']
    ordering = ['-date']


@admin.register(WeeklyAggregation)
class WeeklyAggregationAdmin(admin.ModelAdmin):
    """Admin interface for WeeklyAggregation model."""

    list_display = ['company', 'year', 'week_number', 'week_start', 'updated_at']
    list_filter = ['year', 'week_number', 'updated_at']
    search_fields = ['company__name']
    readonly_fields = ['updated_at']
    ordering = ['-year', '-week_number']


@admin.register(MonthlyAggregation)
class MonthlyAggregationAdmin(admin.ModelAdmin):
    """Admin interface for MonthlyAggregation model."""

    list_display = ['company', 'year', 'month', 'updated_at']
    list_filter = ['year', 'month', 'updated_at']
    search_fields = ['company__name']
    readonly_fields = ['updated_at']
    ordering = ['-year', '-month']


@admin.register(QuarterlyAggregation)
class QuarterlyAggregationAdmin(admin.ModelAdmin):
    """Admin interface for QuarterlyAggregation model."""

    list_display = ['company', 'year', 'quarter', 'updated_at']
    list_filter = ['year', 'quarter', 'updated_at']
    search_fields = ['company__name']
    readonly_fields = ['updated_at']
    ordering = ['-year', '-quarter']


@admin.register(YearlyAggregation)
class YearlyAggregationAdmin(admin.ModelAdmin):
    """Admin interface for YearlyAggregation model."""

    list_display = ['company', 'year', 'updated_at']
    list_filter = ['year', 'updated_at']
    search_fields = ['company__name']
    readonly_fields = ['updated_at']
    ordering = ['-year']


@admin.register(ProductAggregation)
class ProductAggregationAdmin(admin.ModelAdmin):
    """Admin interface for ProductAggregation model."""

    list_display = ['company', 'product_id', 'period', 'period_type', 'updated_at']
    list_filter = ['period_type', 'updated_at']
    search_fields = ['company__name', 'product_id']
    readonly_fields = ['updated_at']
    ordering = ['-period']


@admin.register(CustomerAggregation)
class CustomerAggregationAdmin(admin.ModelAdmin):
    """Admin interface for CustomerAggregation model."""

    list_display = ['company', 'customer_id', 'period', 'period_type', 'updated_at']
    list_filter = ['period_type', 'updated_at']
    search_fields = ['company__name', 'customer_id']
    readonly_fields = ['updated_at']
    ordering = ['-period']


@admin.register(CategoryAggregation)
class CategoryAggregationAdmin(admin.ModelAdmin):
    """Admin interface for CategoryAggregation model."""

    list_display = ['company', 'category', 'period', 'period_type', 'updated_at']
    list_filter = ['period_type', 'updated_at']
    search_fields = ['company__name', 'category']
    readonly_fields = ['updated_at']
    ordering = ['-period']


@admin.register(Benchmark)
class BenchmarkAdmin(admin.ModelAdmin):
    """Admin interface for Benchmark model."""

    list_display = [
        'industry', 'metric_name', 'value',
        'period', 'period_type', 'sample_size',
        'is_valid', 'created_at'
    ]
    list_filter = ['industry', 'period_type', 'created_at']
    search_fields = ['industry', 'metric_name']
    readonly_fields = ['created_at', 'updated_at', 'is_valid']
    ordering = ['-created_at']

    def is_valid(self, obj):
        """Display validity status in admin."""
        return obj.is_valid
    is_valid.boolean = True
    is_valid.short_description = 'Valid (≥10 companies)'

    fieldsets = (
        ('Basic Information', {
            'fields': ('industry', 'metric_name', 'value')
        }),
        ('Period', {
            'fields': ('period', 'period_type')
        }),
        ('Statistics', {
            'fields': ('sample_size', 'percentile_25', 'percentile_50', 'percentile_75')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
