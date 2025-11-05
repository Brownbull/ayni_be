"""
Django wrapper for GabeDA feature engine integration.

This module provides a clean interface between Django and the existing
GabeDA engine located in ayni_core/src/. It handles:
- DataFrame conversion from Django models
- Column mapping application
- GabeDA execution
- Result persistence to database
- Multi-level aggregation storage

Architecture:
- GabeDA engine (ayni_core/src/) - Pure Python feature engine
- This wrapper - Django-specific integration layer
- Celery tasks (tasks.py) - Async processing orchestration
"""

import sys
import os
import logging
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from django.conf import settings
from django.db import transaction

# Add ayni_core to Python path for GabeDA imports
AYNI_CORE_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / 'ayni_core'
if str(AYNI_CORE_PATH) not in sys.path:
    sys.path.insert(0, str(AYNI_CORE_PATH))

# Import GabeDA components
from src.core.context import GabedaContext
from src.core.constants import (
    COLUMN_SCHEMA,
    REQUIRED_COLUMNS,
    OPTIONAL_COLUMNS,
    INFERABLE_COLUMNS,
    DEFAULT_FLOAT,
    DEFAULT_INT,
    DEFAULT_STRING
)
from src.execution.orchestrator import ExecutionOrchestrator
from src.execution.executor import ModelExecutor
from src.preprocessing.loaders import load_csv
from src.preprocessing.transformers import standardize_columns, infer_missing_columns
from src.preprocessing.validators import validate_schema, validate_business_rules
from src.utils.logger import get_logger

# Django imports
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

logger = get_logger(__name__)


class GabedaProcessingError(Exception):
    """Base exception for GabeDA processing errors."""
    pass


class GabedaValidationError(GabedaProcessingError):
    """Raised when data validation fails."""
    pass


class GabedaWrapper:
    """
    Django wrapper for GabeDA feature engine.

    This class provides a clean interface between Django's ORM and the
    pure Python GabeDA engine. It handles data flow in both directions:
    - Django → GabeDA: CSV upload → DataFrame → Feature processing
    - GabeDA → Django: Processed features → Aggregations → Database

    Key Responsibilities:
    1. Load and validate CSV files
    2. Apply user-defined column mappings
    3. Execute GabeDA feature engine
    4. Store multi-level aggregations in database
    5. Track data updates for transparency
    6. Maintain data quality standards (95% minimum)
    """

    def __init__(self, upload: Upload):
        """
        Initialize wrapper with an Upload instance.

        Args:
            upload: Django Upload model instance

        Raises:
            ValueError: If upload has no file or company
        """
        if not upload.file:
            raise ValueError(f"Upload {upload.id} has no file attached")
        if not upload.company:
            raise ValueError(f"Upload {upload.id} has no company attached")

        self.upload = upload
        self.company = upload.company
        self.column_mapping = upload.column_mapping or {}

        # GabeDA components (initialized on demand)
        self.context: Optional[GabedaContext] = None
        self.orchestrator: Optional[ExecutionOrchestrator] = None

        # Processing state
        self.df_raw: Optional[pd.DataFrame] = None
        self.df_processed: Optional[pd.DataFrame] = None
        self.data_quality_score: Optional[float] = None

    def load_and_validate_csv(self) -> pd.DataFrame:
        """
        Load CSV file and perform initial validation.

        This step:
        1. Loads CSV into DataFrame
        2. Applies user-defined column mappings
        3. Validates required columns exist
        4. Validates data types
        5. Performs basic data quality checks

        Returns:
            pd.DataFrame: Raw DataFrame with mapped columns

        Raises:
            GabedaValidationError: If validation fails
        """
        logger.info(f"Loading CSV for upload {self.upload.id}")

        try:
            # Load CSV using GabeDA's loader
            df = load_csv(self.upload.file.path)
            logger.info(f"Loaded CSV: {len(df)} rows, {len(df.columns)} columns")

            # Apply column mapping
            df = self._apply_column_mapping(df)

            # Validate schema
            validation_result = validate_schema(df, COLUMN_SCHEMA)
            if not validation_result['valid']:
                errors = validation_result['errors']
                raise GabedaValidationError(
                    f"Schema validation failed: {errors}"
                )

            # Validate business rules
            business_validation = validate_business_rules(df)
            if not business_validation['valid']:
                logger.warning(
                    f"Business rule violations found: {business_validation['warnings']}"
                )

            self.df_raw = df
            logger.info(f"CSV validation successful: {len(df)} valid rows")
            return df

        except Exception as e:
            logger.error(f"CSV loading failed: {str(e)}")
            raise GabedaValidationError(f"Failed to load CSV: {str(e)}")

    def _apply_column_mapping(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply user-defined column mappings to DataFrame.

        This transforms user's column names to GabeDA's expected schema.
        For example: {"fecha": "in_dt", "producto": "in_product_id"}

        Args:
            df: Raw DataFrame with user column names

        Returns:
            pd.DataFrame: DataFrame with standardized column names
        """
        if not self.column_mapping:
            logger.warning("No column mapping provided, using columns as-is")
            return df

        # Create reverse mapping (user_column → gabeda_column)
        rename_map = {v: k for k, v in self.column_mapping.items()}

        # Rename columns
        df_mapped = df.rename(columns=rename_map)

        logger.info(f"Applied column mapping: {list(rename_map.keys())}")
        return df_mapped

    def preprocess_data(self) -> pd.DataFrame:
        """
        Preprocess data for GabeDA processing.

        This step:
        1. Standardizes column formats (dates, numbers)
        2. Infers missing optional columns
        3. Applies default values for nulls
        4. Validates data quality

        Returns:
            pd.DataFrame: Preprocessed DataFrame ready for feature engine

        Raises:
            GabedaProcessingError: If preprocessing fails
        """
        if self.df_raw is None:
            raise GabedaProcessingError("Must load CSV before preprocessing")

        logger.info("Preprocessing data")

        try:
            df = self.df_raw.copy()

            # Standardize columns (dates, types, formats)
            df = standardize_columns(df, COLUMN_SCHEMA)

            # Infer missing columns where possible
            df = infer_missing_columns(df, INFERABLE_COLUMNS)

            # Calculate data quality score
            self.data_quality_score = self._calculate_data_quality(df)
            logger.info(f"Data quality score: {self.data_quality_score:.1f}%")

            # Check minimum quality threshold (95%)
            if self.data_quality_score < 95.0:
                raise GabedaValidationError(
                    f"Data quality below threshold: {self.data_quality_score:.1f}% < 95.0%"
                )

            self.df_processed = df
            logger.info(f"Preprocessing complete: {len(df)} rows")
            return df

        except Exception as e:
            logger.error(f"Preprocessing failed: {str(e)}")
            raise GabedaProcessingError(f"Preprocessing failed: {str(e)}")

    def _calculate_data_quality(self, df: pd.DataFrame) -> float:
        """
        Calculate overall data quality score based on 6 dimensions.

        Dimensions (from data-quality-standard.md):
        1. Completeness (20%) - No missing required fields
        2. Accuracy (20%) - Values within expected ranges
        3. Consistency (20%) - Uniform formats
        4. Timeliness (15%) - Data freshness
        5. Uniqueness (15%) - No duplicates
        6. Validity (10%) - Correct formats and types

        Returns:
            float: Overall quality score (0-100)
        """
        scores = {}

        # 1. Completeness (20%)
        required_cols = [c for c in REQUIRED_COLUMNS if c in df.columns]
        completeness = (df[required_cols].notna().sum().sum() /
                       (len(df) * len(required_cols)) * 100)
        scores['completeness'] = completeness

        # 2. Accuracy (20%) - Check value ranges
        accuracy = 100.0  # Start at 100%
        if 'in_quantity' in df.columns:
            invalid_qty = (df['in_quantity'] <= 0).sum()
            accuracy -= (invalid_qty / len(df)) * 20
        if 'in_price_total' in df.columns:
            invalid_price = (df['in_price_total'] <= 0).sum()
            accuracy -= (invalid_price / len(df)) * 20
        scores['accuracy'] = max(accuracy, 0)

        # 3. Consistency (20%) - Check format consistency
        consistency = 100.0
        # Check if dates are consistent format
        if 'in_dt' in df.columns:
            try:
                pd.to_datetime(df['in_dt'])
            except:
                consistency -= 20
        scores['consistency'] = max(consistency, 0)

        # 4. Timeliness (15%) - Check data freshness
        timeliness = 100.0
        if 'in_dt' in df.columns:
            try:
                latest_date = pd.to_datetime(df['in_dt']).max()
                days_old = (pd.Timestamp.now() - latest_date).days
                if days_old > 90:
                    timeliness = 80.0
                elif days_old > 30:
                    timeliness = 90.0
            except:
                timeliness = 100.0  # Can't determine, assume OK
        scores['timeliness'] = timeliness

        # 5. Uniqueness (15%) - Check for duplicates
        if 'in_trans_id' in df.columns:
            duplicates = df['in_trans_id'].duplicated().sum()
            uniqueness = max(100 - (duplicates / len(df)) * 100, 0)
        else:
            uniqueness = 100.0
        scores['uniqueness'] = uniqueness

        # 6. Validity (10%) - Check data types
        validity = 100.0
        for col, schema in COLUMN_SCHEMA.items():
            if col in df.columns:
                expected_dtype = schema['dtype']
                if expected_dtype == 'datetime64[ns]':
                    try:
                        pd.to_datetime(df[col])
                    except:
                        validity -= 10
                elif expected_dtype == 'float64':
                    if not pd.api.types.is_numeric_dtype(df[col]):
                        validity -= 10
        scores['validity'] = max(validity, 0)

        # Calculate weighted score
        overall_score = (
            scores['completeness'] * 0.20 +
            scores['accuracy'] * 0.20 +
            scores['consistency'] * 0.20 +
            scores['timeliness'] * 0.15 +
            scores['uniqueness'] * 0.15 +
            scores['validity'] * 0.10
        )

        logger.info(f"Data quality breakdown: {scores}")
        return overall_score

    def execute_gabeda_engine(self) -> Dict[str, Any]:
        """
        Execute GabeDA feature engine on preprocessed data.

        This step:
        1. Initializes GabeDA context
        2. Loads preprocessed data into context
        3. Executes feature calculation pipeline
        4. Generates multi-level aggregations
        5. Returns processed results

        Returns:
            dict: Processing results with all aggregation levels

        Raises:
            GabedaProcessingError: If execution fails
        """
        if self.df_processed is None:
            raise GabedaProcessingError("Must preprocess data before executing GabeDA")

        logger.info("Executing GabeDA feature engine")

        try:
            # Initialize GabeDA context
            self.context = GabedaContext()
            self.context.set_dataset('preprocessed', self.df_processed)

            # Initialize executor and orchestrator
            executor = ModelExecutor(self.context)
            self.orchestrator = ExecutionOrchestrator(executor, self.context)

            # Define feature calculation models
            # (Simplified for MVP - extend with real feature configs later)
            models = self._get_feature_models()

            # Execute pipeline
            results = self.orchestrator.execute_pipeline(
                models=models,
                initial_dataset_name='preprocessed'
            )

            logger.info(f"GabeDA execution complete: {len(results)} models executed")
            return results

        except Exception as e:
            logger.error(f"GabeDA execution failed: {str(e)}")
            raise GabedaProcessingError(f"GabeDA execution failed: {str(e)}")

    def _get_feature_models(self) -> List[Dict[str, Any]]:
        """
        Define feature calculation models for GabeDA.

        For MVP, we create basic aggregation models. In future iterations,
        this will load from configuration files or database.

        Returns:
            list: List of model specifications
        """
        # MVP: Basic daily, monthly, product aggregations
        # Full feature set will be added in future tasks
        return [
            {
                'name': 'daily_agg',
                'config': {
                    'model_name': 'daily_agg',
                    'groupby_cols': ['in_dt'],
                    'exec_seq': ['sum', 'count', 'mean']
                },
                'input_dataset': 'preprocessed'
            },
            {
                'name': 'product_agg',
                'config': {
                    'model_name': 'product_agg',
                    'groupby_cols': ['in_product_id'],
                    'exec_seq': ['sum', 'count', 'mean']
                },
                'input_dataset': 'preprocessed'
            }
        ]

    @transaction.atomic
    def persist_to_database(self) -> Dict[str, int]:
        """
        Persist processed data to Django database.

        This step:
        1. Saves raw transactions
        2. Creates multi-level aggregations (daily, monthly, product, etc.)
        3. Tracks data updates (rows_before, rows_after, rows_updated)
        4. Creates audit trail

        Returns:
            dict: Counts of created/updated records by type

        Raises:
            GabedaProcessingError: If database persistence fails
        """
        if self.df_processed is None:
            raise GabedaProcessingError("No processed data to persist")

        logger.info("Persisting data to database")

        try:
            counts = {
                'raw_transactions': 0,
                'daily_aggregations': 0,
                'monthly_aggregations': 0,
                'product_aggregations': 0,
            }

            # Save raw transactions
            raw_trans_count = self._save_raw_transactions()
            counts['raw_transactions'] = raw_trans_count

            # Generate and save aggregations
            # (Simplified for MVP - full aggregation logic in future tasks)
            daily_count = self._save_daily_aggregations()
            counts['daily_aggregations'] = daily_count

            monthly_count = self._save_monthly_aggregations()
            counts['monthly_aggregations'] = monthly_count

            product_count = self._save_product_aggregations()
            counts['product_aggregations'] = product_count

            # Track data update
            self._track_data_update(counts)

            logger.info(f"Database persistence complete: {counts}")
            return counts

        except Exception as e:
            logger.error(f"Database persistence failed: {str(e)}")
            raise GabedaProcessingError(f"Database persistence failed: {str(e)}")

    def _save_raw_transactions(self) -> int:
        """Save raw transaction data."""
        transactions = []
        for _, row in self.df_processed.iterrows():
            trans = RawTransaction(
                company=self.company,
                upload=self.upload,
                data=row.to_dict(),
                processed_at=timezone.now()
            )
            transactions.append(trans)

        RawTransaction.objects.bulk_create(transactions, batch_size=1000)
        return len(transactions)

    def _save_daily_aggregations(self) -> int:
        """Generate and save daily aggregations."""
        # MVP: Simplified aggregation
        # Full GabeDA aggregation output will be integrated in future
        df = self.df_processed
        daily_groups = df.groupby(pd.Grouper(key='in_dt', freq='D'))

        aggregations = []
        for date, group in daily_groups:
            if len(group) == 0:
                continue

            metrics = {
                'total_revenue': float(group['in_price_total'].sum()),
                'total_quantity': float(group['in_quantity'].sum()),
                'transaction_count': len(group),
                'avg_transaction_value': float(group['in_price_total'].mean()),
            }

            agg = DailyAggregation(
                company=self.company,
                date=date.date(),
                metrics=metrics
            )
            aggregations.append(agg)

        if aggregations:
            DailyAggregation.objects.bulk_create(
                aggregations,
                update_conflicts=True,
                update_fields=['metrics'],
                unique_fields=['company', 'date']
            )

        return len(aggregations)

    def _save_monthly_aggregations(self) -> int:
        """Generate and save monthly aggregations."""
        df = self.df_processed
        df['year_month'] = pd.to_datetime(df['in_dt']).dt.to_period('M')

        aggregations = []
        for period, group in df.groupby('year_month'):
            if len(group) == 0:
                continue

            metrics = {
                'total_revenue': float(group['in_price_total'].sum()),
                'total_quantity': float(group['in_quantity'].sum()),
                'transaction_count': len(group),
                'avg_transaction_value': float(group['in_price_total'].mean()),
                'unique_products': int(group['in_product_id'].nunique()),
            }

            agg = MonthlyAggregation(
                company=self.company,
                month=period.month,
                year=period.year,
                metrics=metrics
            )
            aggregations.append(agg)

        if aggregations:
            MonthlyAggregation.objects.bulk_create(
                aggregations,
                update_conflicts=True,
                update_fields=['metrics'],
                unique_fields=['company', 'year', 'month']
            )

        return len(aggregations)

    def _save_product_aggregations(self) -> int:
        """Generate and save product-level aggregations."""
        df = self.df_processed

        aggregations = []
        for product_id, group in df.groupby('in_product_id'):
            metrics = {
                'total_revenue': float(group['in_price_total'].sum()),
                'total_quantity': float(group['in_quantity'].sum()),
                'transaction_count': len(group),
                'avg_price': float(group['in_price_total'].mean() / group['in_quantity'].mean()),
            }

            agg = ProductAggregation(
                company=self.company,
                product_id=str(product_id),
                period='all_time',  # MVP: All-time aggregation
                metrics=metrics
            )
            aggregations.append(agg)

        if aggregations:
            ProductAggregation.objects.bulk_create(
                aggregations,
                update_conflicts=True,
                update_fields=['metrics'],
                unique_fields=['company', 'product_id', 'period']
            )

        return len(aggregations)

    def _track_data_update(self, counts: Dict[str, int]):
        """Create data update tracking record."""
        DataUpdate.objects.create(
            company=self.company,
            upload=self.upload,
            period='upload',
            rows_before=0,  # TODO: Count existing rows
            rows_after=counts['raw_transactions'],
            rows_updated=counts['raw_transactions'],
            user=self.upload.uploaded_by
        )

    def process_complete_pipeline(self) -> Dict[str, Any]:
        """
        Execute the complete GabeDA processing pipeline.

        This is the main entry point that orchestrates all steps:
        1. Load and validate CSV
        2. Preprocess data
        3. Execute GabeDA engine
        4. Persist to database
        5. Return comprehensive results

        Returns:
            dict: Complete processing results

        Raises:
            GabedaProcessingError: If any step fails
        """
        logger.info(f"Starting complete pipeline for upload {self.upload.id}")

        try:
            # Step 1: Load and validate
            self.load_and_validate_csv()

            # Step 2: Preprocess
            self.preprocess_data()

            # Step 3: Execute GabeDA (MVP: Simplified)
            # gabeda_results = self.execute_gabeda_engine()

            # Step 4: Persist to database
            db_counts = self.persist_to_database()

            # Compile results
            results = {
                'success': True,
                'upload_id': self.upload.id,
                'company_id': self.company.id,
                'rows_processed': len(self.df_processed),
                'data_quality_score': self.data_quality_score,
                'database_counts': db_counts,
                'processed_at': timezone.now().isoformat(),
            }

            logger.info(f"Pipeline complete: {results}")
            return results

        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            raise GabedaProcessingError(f"Pipeline failed: {str(e)}")


def process_upload_with_gabeda(upload_id: int) -> Dict[str, Any]:
    """
    Convenience function to process an upload with GabeDA.

    This is the main entry point called from Celery tasks.

    Args:
        upload_id: ID of Upload model instance

    Returns:
        dict: Processing results

    Raises:
        GabedaProcessingError: If processing fails
    """
    try:
        upload = Upload.objects.get(id=upload_id)
        wrapper = GabedaWrapper(upload)
        return wrapper.process_complete_pipeline()
    except Upload.DoesNotExist:
        raise GabedaProcessingError(f"Upload {upload_id} not found")
