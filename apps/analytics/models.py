"""
Analytics models for AYNI platform.

This module defines all aggregation models for multi-level analytics:
- Temporal aggregations (daily, weekly, monthly, quarterly, yearly)
- Dimensional aggregations (product, customer, category)
- Benchmarking data

All models use JSONB for flexible metric storage.
"""

from django.db import models
from django.utils import timezone


class DailyAggregation(models.Model):
    """
    Daily-level aggregations for fast queries and detailed analysis.

    Attributes:
        company: Associated company (tenant isolation)
        date: Aggregation date
        metrics: Computed metrics (JSONB)
        updated_at: Last update timestamp
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='daily_aggregations',
        db_index=True
    )
    date = models.DateField(db_index=True)

    # Metrics stored as JSON for flexibility
    metrics = models.JSONField(
        help_text='Daily metrics: revenue, transactions, avg_ticket, etc.'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'daily_aggregations'
        unique_together = ['company', 'date']
        indexes = [
            models.Index(fields=['company', 'date']),
            models.Index(fields=['date']),
        ]
        ordering = ['-date']

    def __str__(self):
        return f"{self.company.name} - {self.date}"


class WeeklyAggregation(models.Model):
    """
    Weekly-level aggregations.

    Attributes:
        company: Associated company
        week_start: Week start date (Monday)
        year: Year
        week_number: ISO week number
        metrics: Computed metrics (JSONB)
        updated_at: Last update timestamp
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='weekly_aggregations',
        db_index=True
    )
    week_start = models.DateField(db_index=True)
    year = models.IntegerField(db_index=True)
    week_number = models.IntegerField()

    metrics = models.JSONField(
        help_text='Weekly metrics aggregated from daily data'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'weekly_aggregations'
        unique_together = ['company', 'year', 'week_number']
        indexes = [
            models.Index(fields=['company', 'year', 'week_number']),
            models.Index(fields=['week_start']),
        ]
        ordering = ['-year', '-week_number']

    def __str__(self):
        return f"{self.company.name} - {self.year}-W{self.week_number:02d}"


class MonthlyAggregation(models.Model):
    """
    Monthly-level aggregations (primary view for PYMEs).

    Attributes:
        company: Associated company
        month: Month (1-12)
        year: Year
        metrics: Computed metrics (JSONB)
        updated_at: Last update timestamp
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='monthly_aggregations',
        db_index=True
    )
    month = models.IntegerField(db_index=True)  # 1-12
    year = models.IntegerField(db_index=True)

    metrics = models.JSONField(
        help_text='Monthly metrics: primary analytics view for PYMEs'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'monthly_aggregations'
        unique_together = ['company', 'year', 'month']
        indexes = [
            models.Index(fields=['company', 'year', 'month']),
            models.Index(fields=['year', 'month']),
        ]
        ordering = ['-year', '-month']

    def __str__(self):
        return f"{self.company.name} - {self.year}-{self.month:02d}"


class QuarterlyAggregation(models.Model):
    """
    Quarterly-level aggregations for trend analysis.

    Attributes:
        company: Associated company
        quarter: Quarter (1-4)
        year: Year
        metrics: Computed metrics (JSONB)
        updated_at: Last update timestamp
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='quarterly_aggregations',
        db_index=True
    )
    quarter = models.IntegerField(db_index=True)  # 1-4
    year = models.IntegerField(db_index=True)

    metrics = models.JSONField(
        help_text='Quarterly metrics for trend analysis'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'quarterly_aggregations'
        unique_together = ['company', 'year', 'quarter']
        indexes = [
            models.Index(fields=['company', 'year', 'quarter']),
            models.Index(fields=['year', 'quarter']),
        ]
        ordering = ['-year', '-quarter']

    def __str__(self):
        return f"{self.company.name} - {self.year}-Q{self.quarter}"


class YearlyAggregation(models.Model):
    """
    Yearly-level aggregations for long-term analysis.

    Attributes:
        company: Associated company
        year: Year
        metrics: Computed metrics (JSONB)
        updated_at: Last update timestamp
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='yearly_aggregations',
        db_index=True
    )
    year = models.IntegerField(db_index=True)

    metrics = models.JSONField(
        help_text='Yearly metrics for annual reports and long-term trends'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'yearly_aggregations'
        unique_together = ['company', 'year']
        indexes = [
            models.Index(fields=['company', 'year']),
            models.Index(fields=['year']),
        ]
        ordering = ['-year']

    def __str__(self):
        return f"{self.company.name} - {self.year}"


class ProductAggregation(models.Model):
    """
    Product-level aggregations across time periods.

    Attributes:
        company: Associated company
        product_id: Product identifier
        period: Time period (e.g., "2024-01" for monthly)
        period_type: Type of period (daily, weekly, monthly, etc.)
        metrics: Product-specific metrics (JSONB)
        updated_at: Last update timestamp
    """

    PERIOD_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('all_time', 'All Time'),
    ]

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='product_aggregations',
        db_index=True
    )
    product_id = models.CharField(max_length=255, db_index=True)
    period = models.CharField(max_length=50)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)

    metrics = models.JSONField(
        help_text='Product metrics: sales, revenue, margin, velocity, etc.'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_aggregations'
        unique_together = ['company', 'product_id', 'period', 'period_type']
        indexes = [
            models.Index(fields=['company', 'product_id', 'period_type']),
            models.Index(fields=['company', 'period_type']),
        ]
        ordering = ['-period']

    def __str__(self):
        return f"{self.company.name} - Product {self.product_id} - {self.period}"


class CustomerAggregation(models.Model):
    """
    Customer-level aggregations across time periods.

    Attributes:
        company: Associated company
        customer_id: Customer identifier
        period: Time period
        period_type: Type of period
        metrics: Customer-specific metrics (JSONB)
        updated_at: Last update timestamp
    """

    PERIOD_TYPE_CHOICES = ProductAggregation.PERIOD_TYPE_CHOICES

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='customer_aggregations',
        db_index=True
    )
    customer_id = models.CharField(max_length=255, db_index=True)
    period = models.CharField(max_length=50)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)

    metrics = models.JSONField(
        help_text='Customer metrics: LTV, frequency, recency, avg_order, etc.'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customer_aggregations'
        unique_together = ['company', 'customer_id', 'period', 'period_type']
        indexes = [
            models.Index(fields=['company', 'customer_id', 'period_type']),
            models.Index(fields=['company', 'period_type']),
        ]
        ordering = ['-period']

    def __str__(self):
        return f"{self.company.name} - Customer {self.customer_id} - {self.period}"


class CategoryAggregation(models.Model):
    """
    Category-level aggregations across time periods.

    Attributes:
        company: Associated company
        category: Category name
        period: Time period
        period_type: Type of period
        metrics: Category-specific metrics (JSONB)
        updated_at: Last update timestamp
    """

    PERIOD_TYPE_CHOICES = ProductAggregation.PERIOD_TYPE_CHOICES

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='category_aggregations',
        db_index=True
    )
    category = models.CharField(max_length=255, db_index=True)
    period = models.CharField(max_length=50)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)

    metrics = models.JSONField(
        help_text='Category metrics: revenue, product_count, top_products, etc.'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'category_aggregations'
        unique_together = ['company', 'category', 'period', 'period_type']
        indexes = [
            models.Index(fields=['company', 'category', 'period_type']),
            models.Index(fields=['company', 'period_type']),
        ]
        ordering = ['-period']

    def __str__(self):
        return f"{self.company.name} - {self.category} - {self.period}"


class Benchmark(models.Model):
    """
    Industry benchmarks for anonymous comparison.

    Aggregates data across multiple companies (minimum 10) to provide
    industry averages while maintaining absolute anonymity.

    Attributes:
        industry: Industry category
        metric_name: Name of the metric
        value: Aggregated metric value
        period: Time period
        period_type: Type of period
        sample_size: Number of companies in sample (must be >= 10)
        created_at: Calculation timestamp
    """

    PERIOD_TYPE_CHOICES = ProductAggregation.PERIOD_TYPE_CHOICES

    industry = models.CharField(max_length=50, db_index=True)
    metric_name = models.CharField(max_length=100, db_index=True)
    value = models.FloatField()

    # Period information
    period = models.CharField(max_length=50)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)

    # Privacy protection
    sample_size = models.IntegerField(
        help_text='Number of companies in benchmark (minimum 10 for privacy)'
    )

    # Statistical measures
    percentile_25 = models.FloatField(null=True, blank=True)
    percentile_50 = models.FloatField(null=True, blank=True)  # Median
    percentile_75 = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'benchmarks'
        unique_together = ['industry', 'metric_name', 'period', 'period_type']
        indexes = [
            models.Index(fields=['industry', 'metric_name']),
            models.Index(fields=['period_type', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.industry} - {self.metric_name} - {self.period}"

    @property
    def is_valid(self):
        """Check if benchmark meets minimum sample size for privacy."""
        return self.sample_size >= 10
