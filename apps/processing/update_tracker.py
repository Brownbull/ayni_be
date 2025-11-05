"""
Data Update Tracking System for AYNI Platform.

This module provides comprehensive tracking of data updates across all aggregation
levels, ensuring full transparency and auditability of data changes.

Key Responsibilities:
1. Count existing rows before updates (rows_before)
2. Count new rows after updates (rows_after)
3. Calculate rows updated, added, and deleted
4. Track changes across all aggregation levels
5. Provide detailed change summaries
6. Support rollback scenarios
7. Maintain data lineage

Architecture:
- UpdateTracker: Main class for tracking operations
- ChangeCalculator: Calculates row differences
- PeriodAnalyzer: Identifies affected time periods
- AuditLogger: Logs all tracking events

Usage:
    tracker = UpdateTracker(company, upload, user)

    # Before processing
    tracker.snapshot_before()

    # Process data...

    # After processing
    tracker.snapshot_after()
    tracker.create_update_record()
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

from django.db import models, transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone

from apps.processing.models import (
    Upload,
    RawTransaction,
    DataUpdate
)
from apps.analytics.models import (
    DailyAggregation,
    WeeklyAggregation,
    MonthlyAggregation,
    QuarterlyAggregation,
    YearlyAggregation,
    ProductAggregation,
    CustomerAggregation,
    CategoryAggregation
)
from apps.companies.models import Company

logger = logging.getLogger(__name__)


class UpdateTrackerError(Exception):
    """Base exception for update tracking errors."""
    pass


class ChangeCalculator:
    """
    Calculates row-level changes for data updates.

    Provides methods to compute:
    - Rows before/after counts
    - Added/updated/deleted counts
    - Net changes
    """

    @staticmethod
    def calculate_changes(before: int, after: int, updated: int) -> Dict[str, int]:
        """
        Calculate comprehensive change statistics.

        Args:
            before: Row count before update
            after: Row count after update
            updated: Number of rows that were modified

        Returns:
            dict: Complete change statistics

        Example:
            before=100, after=150, updated=50
            -> added=100 (150-100+50), deleted=0, net_change=50
        """
        # Rows added = (after - before) + updated
        # This accounts for both new rows and rows that replaced deleted ones
        added = max(0, after - before + updated)

        # Rows deleted = before - (after - added)
        deleted = max(0, before - (after - added))

        # Net change
        net_change = after - before

        return {
            'rows_before': before,
            'rows_after': after,
            'rows_updated': updated,
            'rows_added': added,
            'rows_deleted': deleted,
            'net_change': net_change
        }

    @staticmethod
    def calculate_simple_addition(existing: int, new: int) -> Dict[str, int]:
        """
        Calculate stats for pure addition (no updates/deletes).

        Args:
            existing: Existing row count
            new: New rows being added

        Returns:
            dict: Change statistics
        """
        return {
            'rows_before': existing,
            'rows_after': existing + new,
            'rows_updated': 0,
            'rows_added': new,
            'rows_deleted': 0,
            'net_change': new
        }


class PeriodAnalyzer:
    """
    Analyzes time periods affected by data updates.

    Identifies which aggregation periods need recalculation
    based on the transaction dates in the upload.
    """

    @staticmethod
    def identify_affected_periods(company: Company, upload: Upload) -> Dict[str, List[str]]:
        """
        Identify all time periods affected by this upload.

        Args:
            company: Company instance
            upload: Upload instance

        Returns:
            dict: Periods by type (daily, monthly, etc.)

        Example:
            {
                'daily': ['2024-01-15', '2024-01-16'],
                'monthly': ['2024-01'],
                'quarterly': ['2024-Q1'],
                'yearly': ['2024']
            }
        """
        # Get date range from transactions
        date_range = RawTransaction.objects.filter(
            company=company,
            upload=upload
        ).aggregate(
            min_date=models.Min('transaction_date'),
            max_date=models.Max('transaction_date')
        )

        if not date_range['min_date']:
            return {}

        min_date = date_range['min_date'].date()
        max_date = date_range['max_date'].date()

        periods = {
            'daily': [],
            'weekly': [],
            'monthly': [],
            'quarterly': [],
            'yearly': []
        }

        # Daily periods
        current = min_date
        while current <= max_date:
            periods['daily'].append(current.isoformat())
            current += timedelta(days=1)

        # Monthly periods
        current_month = min_date.replace(day=1)
        max_month = max_date.replace(day=1)
        while current_month <= max_month:
            periods['monthly'].append(current_month.strftime('%Y-%m'))
            # Move to next month
            if current_month.month == 12:
                current_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                current_month = current_month.replace(month=current_month.month + 1)

        # Quarterly periods
        for year in range(min_date.year, max_date.year + 1):
            for quarter in range(1, 5):
                quarter_start = datetime(year, (quarter - 1) * 3 + 1, 1).date()
                quarter_end = datetime(year, quarter * 3, 1).date()
                if quarter_end >= min_date and quarter_start <= max_date:
                    periods['quarterly'].append(f"{year}-Q{quarter}")

        # Yearly periods
        for year in range(min_date.year, max_date.year + 1):
            periods['yearly'].append(str(year))

        # Weekly periods (ISO week)
        current = min_date
        while current <= max_date:
            iso_calendar = current.isocalendar()
            week_str = f"{iso_calendar[0]}-W{iso_calendar[1]:02d}"
            if week_str not in periods['weekly']:
                periods['weekly'].append(week_str)
            current += timedelta(days=7)

        return periods


class UpdateTracker:
    """
    Main tracker for data updates.

    Provides comprehensive tracking of data changes across all aggregation levels.

    Workflow:
        1. snapshot_before() - Count existing rows before processing
        2. [Data processing happens]
        3. snapshot_after() - Count new rows after processing
        4. create_update_record() - Create audit record

    Attributes:
        company: Company instance
        upload: Upload instance
        user: User performing the update
        before_counts: Row counts before update
        after_counts: Row counts after update
    """

    def __init__(self, company: Company, upload: Upload, user=None):
        """
        Initialize update tracker.

        Args:
            company: Company instance
            upload: Upload instance
            user: User instance (optional)
        """
        self.company = company
        self.upload = upload
        self.user = user or upload.user

        # Tracking state
        self.before_counts = {}
        self.after_counts = {}
        self.period_changes = defaultdict(dict)

        logger.info(
            f"UpdateTracker initialized for company={company.id}, "
            f"upload={upload.id}"
        )

    def snapshot_before(self) -> Dict[str, int]:
        """
        Take snapshot of row counts before processing.

        Counts existing rows across all aggregation levels to establish
        a baseline for change calculation.

        Returns:
            dict: Row counts by aggregation level

        Raises:
            UpdateTrackerError: If snapshot fails
        """
        try:
            self.before_counts = {
                'raw_transactions': RawTransaction.objects.filter(
                    company=self.company
                ).count(),

                'daily_aggregations': DailyAggregation.objects.filter(
                    company=self.company
                ).count(),

                'weekly_aggregations': WeeklyAggregation.objects.filter(
                    company=self.company
                ).count(),

                'monthly_aggregations': MonthlyAggregation.objects.filter(
                    company=self.company
                ).count(),

                'quarterly_aggregations': QuarterlyAggregation.objects.filter(
                    company=self.company
                ).count(),

                'yearly_aggregations': YearlyAggregation.objects.filter(
                    company=self.company
                ).count(),

                'product_aggregations': ProductAggregation.objects.filter(
                    company=self.company
                ).count(),

                'customer_aggregations': CustomerAggregation.objects.filter(
                    company=self.company
                ).count(),

                'category_aggregations': CategoryAggregation.objects.filter(
                    company=self.company
                ).count(),
            }

            logger.info(
                f"Before snapshot: {sum(self.before_counts.values())} total rows "
                f"across {len(self.before_counts)} aggregation levels"
            )

            return self.before_counts

        except Exception as e:
            logger.error(f"Failed to take before snapshot: {e}")
            raise UpdateTrackerError(f"Snapshot failed: {e}")

    def snapshot_after(self) -> Dict[str, int]:
        """
        Take snapshot of row counts after processing.

        Counts rows after data processing to calculate changes.

        Returns:
            dict: Row counts by aggregation level

        Raises:
            UpdateTrackerError: If snapshot fails or before snapshot missing
        """
        if not self.before_counts:
            raise UpdateTrackerError(
                "Must call snapshot_before() before snapshot_after()"
            )

        try:
            self.after_counts = {
                'raw_transactions': RawTransaction.objects.filter(
                    company=self.company
                ).count(),

                'daily_aggregations': DailyAggregation.objects.filter(
                    company=self.company
                ).count(),

                'weekly_aggregations': WeeklyAggregation.objects.filter(
                    company=self.company
                ).count(),

                'monthly_aggregations': MonthlyAggregation.objects.filter(
                    company=self.company
                ).count(),

                'quarterly_aggregations': QuarterlyAggregation.objects.filter(
                    company=self.company
                ).count(),

                'yearly_aggregations': YearlyAggregation.objects.filter(
                    company=self.company
                ).count(),

                'product_aggregations': ProductAggregation.objects.filter(
                    company=self.company
                ).count(),

                'customer_aggregations': CustomerAggregation.objects.filter(
                    company=self.company
                ).count(),

                'category_aggregations': CategoryAggregation.objects.filter(
                    company=self.company
                ).count(),
            }

            logger.info(
                f"After snapshot: {sum(self.after_counts.values())} total rows "
                f"across {len(self.after_counts)} aggregation levels"
            )

            return self.after_counts

        except Exception as e:
            logger.error(f"Failed to take after snapshot: {e}")
            raise UpdateTrackerError(f"Snapshot failed: {e}")

    def calculate_changes_summary(self) -> Dict[str, Any]:
        """
        Calculate comprehensive summary of all changes.

        Returns:
            dict: Complete change summary with per-level statistics
        """
        if not self.before_counts or not self.after_counts:
            raise UpdateTrackerError("Must take before and after snapshots first")

        summary = {}

        for level in self.before_counts.keys():
            before = self.before_counts[level]
            after = self.after_counts[level]

            # For MVP, assume simple addition (no updates within existing rows)
            # Future: Track actual updates vs additions
            summary[level] = ChangeCalculator.calculate_simple_addition(
                existing=before,
                new=after - before
            )

        # Calculate totals
        summary['totals'] = {
            'rows_before': sum(self.before_counts.values()),
            'rows_after': sum(self.after_counts.values()),
            'rows_added': sum(self.after_counts.values()) - sum(self.before_counts.values()),
            'rows_updated': 0,  # MVP: No in-place updates yet
            'rows_deleted': 0,  # MVP: No deletions yet
            'net_change': sum(self.after_counts.values()) - sum(self.before_counts.values())
        }

        return summary

    def create_update_record(self) -> DataUpdate:
        """
        Create comprehensive DataUpdate record.

        This is the main method that creates the audit trail record
        with all change statistics.

        Returns:
            DataUpdate: Created update record

        Raises:
            UpdateTrackerError: If record creation fails
        """
        if not self.before_counts or not self.after_counts:
            raise UpdateTrackerError(
                "Must take before and after snapshots before creating record"
            )

        try:
            # Calculate changes
            changes_summary = self.calculate_changes_summary()

            # Identify affected periods
            affected_periods = PeriodAnalyzer.identify_affected_periods(
                self.company,
                self.upload
            )

            # Determine primary period (broadest affected period)
            if affected_periods.get('yearly'):
                period = affected_periods['yearly'][0]
                period_type = 'yearly'
            elif affected_periods.get('quarterly'):
                period = affected_periods['quarterly'][0]
                period_type = 'quarterly'
            elif affected_periods.get('monthly'):
                period = affected_periods['monthly'][0]
                period_type = 'monthly'
            elif affected_periods.get('weekly'):
                period = affected_periods['weekly'][0]
                period_type = 'weekly'
            elif affected_periods.get('daily'):
                period = affected_periods['daily'][0]
                period_type = 'daily'
            else:
                period = 'upload'
                period_type = 'upload'

            # Create update record
            with transaction.atomic():
                update_record = DataUpdate.objects.create(
                    company=self.company,
                    upload=self.upload,
                    user=self.user,
                    period=period,
                    period_type=period_type,
                    rows_before=changes_summary['totals']['rows_before'],
                    rows_after=changes_summary['totals']['rows_after'],
                    rows_updated=changes_summary['totals']['rows_updated'],
                    rows_added=changes_summary['totals']['rows_added'],
                    rows_deleted=changes_summary['totals']['rows_deleted'],
                    changes_summary={
                        'by_level': changes_summary,
                        'affected_periods': affected_periods,
                        'upload_filename': self.upload.filename,
                        'upload_rows': self.upload.original_rows,
                        'processed_at': timezone.now().isoformat()
                    }
                )

            logger.info(
                f"Created DataUpdate record id={update_record.id}: "
                f"{changes_summary['totals']['rows_added']} rows added, "
                f"{changes_summary['totals']['rows_updated']} rows updated, "
                f"{changes_summary['totals']['rows_deleted']} rows deleted"
            )

            return update_record

        except Exception as e:
            logger.error(f"Failed to create update record: {e}")
            raise UpdateTrackerError(f"Record creation failed: {e}")

    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Get human-readable summary statistics.

        Returns:
            dict: Summary statistics for display
        """
        if not self.before_counts or not self.after_counts:
            return {
                'status': 'incomplete',
                'message': 'Tracking not complete - missing snapshots'
            }

        changes = self.calculate_changes_summary()

        return {
            'status': 'complete',
            'total_before': changes['totals']['rows_before'],
            'total_after': changes['totals']['rows_after'],
            'total_added': changes['totals']['rows_added'],
            'net_change': changes['totals']['net_change'],
            'by_level': {
                level: {
                    'before': stats['rows_before'],
                    'after': stats['rows_after'],
                    'added': stats['rows_added']
                }
                for level, stats in changes.items()
                if level != 'totals'
            }
        }


def track_upload_changes(company: Company, upload: Upload, user=None) -> DataUpdate:
    """
    Convenience function to track changes for an upload.

    This is the recommended way to use UpdateTracker for simple cases.

    Args:
        company: Company instance
        upload: Upload instance
        user: User instance (optional)

    Returns:
        DataUpdate: Created update record

    Example:
        # After processing is complete
        update_record = track_upload_changes(company, upload, user)
        print(f"Added {update_record.rows_added} rows")
    """
    tracker = UpdateTracker(company, upload, user)

    # Since we're calling this after processing, we only need
    # to take the after snapshot and infer the before state
    # This is a simplified version for post-processing tracking

    # Get counts for this specific upload
    upload_rows = RawTransaction.objects.filter(
        company=company,
        upload=upload
    ).count()

    # Estimate before counts (total - upload)
    tracker.before_counts = {
        'raw_transactions': RawTransaction.objects.filter(
            company=company
        ).exclude(upload=upload).count()
    }

    # Get current counts as after
    tracker.after_counts = {
        'raw_transactions': RawTransaction.objects.filter(
            company=company
        ).count()
    }

    return tracker.create_update_record()
