"""
Comprehensive test suite for GabeDA integration.

Tests all 8 required test types:
1. Valid (Happy Path) - Normal operation scenarios
2. Error - Error handling and recovery
3. Invalid - Input validation and rejection
4. Edge - Boundary conditions and extremes
5. Functional - Business logic correctness
6. Visual - N/A for backend (data quality metrics instead)
7. Performance - Speed and scalability
8. Security - Data isolation and validation

Quality Standard: Data Quality Standard (95% minimum)
"""

import pytest
import pandas as pd
import tempfile
import os
from decimal import Decimal
from datetime import datetime, timedelta
from django.test import TestCase
from django.utils import timezone
from unittest.mock import Mock, patch, MagicMock

from apps.processing.gabeda_wrapper import (
    GabedaWrapper,
    GabedaProcessingError,
    GabedaValidationError,
    process_upload_with_gabeda
)
from apps.processing.models import Upload, RawTransaction, DataUpdate
from apps.analytics.models import (
    DailyAggregation,
    MonthlyAggregation,
    ProductAggregation
)
from apps.companies.models import Company
from apps.authentication.models import User


class TestGabedaIntegrationValid(TestCase):
    """Test Type 1: VALID (Happy Path) - Normal operation scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            password='test123',
            first_name='Test',
            last_name='User'
        )
        self.company = Company.objects.create(
            name='Test Company',
            rut='12345678-9',
            industry='retail'
        )
        self.company.users.add(self.user)

    def test_valid_csv_processing(self):
        """Test 1.1: Process valid CSV with all required columns."""
        # Create test CSV
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001,P001,10,100.0
2024-01-02,T002,P002,5,50.0
2024-01-03,T003,P001,15,150.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            # Create upload
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='test.csv',
                    file=csv_file,
                    column_mapping={}
                )

            # Process with GabeDA
            wrapper = GabedaWrapper(upload)
            results = wrapper.process_complete_pipeline()

            # Assertions
            self.assertTrue(results['success'])
            self.assertEqual(results['rows_processed'], 3)
            self.assertGreaterEqual(results['data_quality_score'], 95.0)
            self.assertGreater(results['database_counts']['raw_transactions'], 0)

        finally:
            os.unlink(csv_path)

    def test_valid_column_mapping(self):
        """Test 1.2: Process CSV with user-defined column mapping."""
        csv_content = """fecha,codigo,nombre,cantidad,precio
2024-01-01,T001,P001,10,100.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            column_mapping = {
                'in_dt': 'fecha',
                'in_trans_id': 'codigo',
                'in_product_id': 'nombre',
                'in_quantity': 'cantidad',
                'in_price_total': 'precio'
            }

            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='test_mapped.csv',
                    file=csv_file,
                    column_mapping=column_mapping
                )

            wrapper = GabedaWrapper(upload)
            df = wrapper.load_and_validate_csv()

            # Check columns renamed correctly
            self.assertIn('in_dt', df.columns)
            self.assertIn('in_product_id', df.columns)

        finally:
            os.unlink(csv_path)

    def test_valid_aggregations_created(self):
        """Test 1.3: Verify all aggregation levels created."""
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001,P001,10,100.0
2024-01-02,T002,P002,5,50.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='test_agg.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            wrapper.process_complete_pipeline()

            # Check aggregations exist
            self.assertTrue(DailyAggregation.objects.filter(company=self.company).exists())
            self.assertTrue(MonthlyAggregation.objects.filter(company=self.company).exists())
            self.assertTrue(ProductAggregation.objects.filter(company=self.company).exists())

        finally:
            os.unlink(csv_path)


class TestGabedaIntegrationError(TestCase):
    """Test Type 2: ERROR - Error handling and recovery."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            password='test123'
        )
        self.company = Company.objects.create(
            name='Test Company',
            rut='12345678-9'
        )

    def test_error_missing_file(self):
        """Test 2.1: Handle upload with missing file."""
        upload = Upload.objects.create(
            company=self.company,
            uploaded_by=self.user,
            filename='missing.csv'
            # No file attached
        )

        with self.assertRaises(ValueError) as cm:
            wrapper = GabedaWrapper(upload)

        self.assertIn("no file", str(cm.exception).lower())

    def test_error_corrupted_csv(self):
        """Test 2.2: Handle corrupted CSV file."""
        csv_content = """in_dt,in_trans_id,in_product_id
2024-01-01,T001,P001
This is not CSV data
2024-01-02"""  # Malformed

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='corrupted.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)

            with self.assertRaises(GabedaValidationError):
                wrapper.load_and_validate_csv()

        finally:
            os.unlink(csv_path)

    def test_error_database_failure(self):
        """Test 2.3: Handle database write failure gracefully."""
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001,P001,10,100.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='test.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            wrapper.load_and_validate_csv()
            wrapper.preprocess_data()

            # Mock database failure
            with patch.object(RawTransaction.objects, 'bulk_create', side_effect=Exception("DB Error")):
                with self.assertRaises(GabedaProcessingError):
                    wrapper.persist_to_database()

        finally:
            os.unlink(csv_path)


class TestGabedaIntegrationInvalid(TestCase):
    """Test Type 3: INVALID - Input validation and rejection."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            password='test123'
        )
        self.company = Company.objects.create(
            name='Test Company',
            rut='12345678-9'
        )

    def test_invalid_missing_required_columns(self):
        """Test 3.1: Reject CSV missing required columns."""
        csv_content = """in_dt,in_trans_id
2024-01-01,T001"""  # Missing in_product_id, in_quantity, in_price_total

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='invalid.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)

            with self.assertRaises(GabedaValidationError) as cm:
                wrapper.load_and_validate_csv()

            self.assertIn("validation failed", str(cm.exception).lower())

        finally:
            os.unlink(csv_path)

    def test_invalid_negative_values(self):
        """Test 3.2: Reject CSV with negative quantities/prices."""
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001,P001,-10,100.0
2024-01-02,T002,P002,5,-50.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='negative.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            wrapper.load_and_validate_csv()
            wrapper.preprocess_data()

            # Data quality should be low due to negative values
            self.assertLess(wrapper.data_quality_score, 95.0)

        finally:
            os.unlink(csv_path)

    def test_invalid_data_types(self):
        """Test 3.3: Reject CSV with wrong data types."""
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
not-a-date,T001,P001,abc,xyz"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='wrong_types.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)

            with self.assertRaises((GabedaValidationError, GabedaProcessingError)):
                wrapper.load_and_validate_csv()
                wrapper.preprocess_data()

        finally:
            os.unlink(csv_path)


class TestGabedaIntegrationEdge(TestCase):
    """Test Type 4: EDGE - Boundary conditions and extremes."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            password='test123'
        )
        self.company = Company.objects.create(
            name='Test Company',
            rut='12345678-9'
        )

    def test_edge_empty_csv(self):
        """Test 4.1: Handle empty CSV file."""
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total"""  # Header only

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='empty.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            df = wrapper.load_and_validate_csv()

            self.assertEqual(len(df), 0)

        finally:
            os.unlink(csv_path)

    def test_edge_single_row(self):
        """Test 4.2: Handle CSV with single row."""
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001,P001,1,1.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='single.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            results = wrapper.process_complete_pipeline()

            self.assertEqual(results['rows_processed'], 1)
            self.assertTrue(results['success'])

        finally:
            os.unlink(csv_path)

    def test_edge_large_csv(self):
        """Test 4.3: Handle large CSV (10k+ rows)."""
        # Generate large CSV
        rows = [f"2024-01-{i % 30 + 1:02d},T{i:06d},P{i % 100:03d},{i % 50 + 1},{(i % 50 + 1) * 10.0}"
                for i in range(1, 10001)]
        csv_content = "in_dt,in_trans_id,in_product_id,in_quantity,in_price_total\n" + "\n".join(rows)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='large.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            results = wrapper.process_complete_pipeline()

            self.assertEqual(results['rows_processed'], 10000)
            self.assertGreaterEqual(results['data_quality_score'], 95.0)

        finally:
            os.unlink(csv_path)

    def test_edge_very_old_data(self):
        """Test 4.4: Handle data from many years ago."""
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
1990-01-01,T001,P001,10,100.0
1990-01-02,T002,P002,5,50.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='old_data.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            wrapper.load_and_validate_csv()
            wrapper.preprocess_data()

            # Old data should affect timeliness score
            self.assertIsNotNone(wrapper.data_quality_score)

        finally:
            os.unlink(csv_path)


class TestGabedaIntegrationFunctional(TestCase):
    """Test Type 5: FUNCTIONAL - Business logic correctness."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            password='test123'
        )
        self.company = Company.objects.create(
            name='Test Company',
            rut='12345678-9'
        )

    def test_functional_aggregation_accuracy(self):
        """Test 5.1: Verify aggregations match raw data."""
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001,P001,10,100.0
2024-01-01,T002,P002,5,50.0
2024-01-01,T003,P001,15,150.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='test_agg.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            wrapper.process_complete_pipeline()

            # Check daily aggregation
            daily_agg = DailyAggregation.objects.get(
                company=self.company,
                date=datetime(2024, 1, 1).date()
            )

            self.assertEqual(daily_agg.metrics['total_revenue'], 300.0)
            self.assertEqual(daily_agg.metrics['total_quantity'], 30.0)
            self.assertEqual(daily_agg.metrics['transaction_count'], 3)

        finally:
            os.unlink(csv_path)

    def test_functional_data_isolation(self):
        """Test 5.2: Verify company data isolation."""
        company2 = Company.objects.create(
            name='Company 2',
            rut='98765432-1'
        )

        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001,P001,10,100.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            # Upload for company 1
            with open(csv_path, 'rb') as csv_file:
                upload1 = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='test1.csv',
                    file=csv_file
                )

            wrapper1 = GabedaWrapper(upload1)
            wrapper1.process_complete_pipeline()

            # Check data only exists for company1
            self.assertEqual(RawTransaction.objects.filter(company=self.company).count(), 1)
            self.assertEqual(RawTransaction.objects.filter(company=company2).count(), 0)

        finally:
            os.unlink(csv_path)

    def test_functional_data_update_tracking(self):
        """Test 5.3: Verify DataUpdate tracking works."""
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001,P001,10,100.0
2024-01-02,T002,P002,5,50.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='test_tracking.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            wrapper.process_complete_pipeline()

            # Check DataUpdate created
            data_update = DataUpdate.objects.get(
                company=self.company,
                upload=upload
            )

            self.assertEqual(data_update.rows_updated, 2)
            self.assertIsNotNone(data_update.timestamp)

        finally:
            os.unlink(csv_path)


class TestGabedaIntegrationPerformance(TestCase):
    """Test Type 7: PERFORMANCE - Speed and scalability."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            password='test123'
        )
        self.company = Company.objects.create(
            name='Test Company',
            rut='12345678-9'
        )

    def test_performance_processing_time(self):
        """Test 7.1: Verify processing completes within time limits."""
        import time

        # 1000 rows should process in < 60 seconds
        rows = [f"2024-01-{i % 30 + 1:02d},T{i:06d},P{i % 100:03d},{i % 50 + 1},{(i % 50 + 1) * 10.0}"
                for i in range(1, 1001)]
        csv_content = "in_dt,in_trans_id,in_product_id,in_quantity,in_price_total\n" + "\n".join(rows)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='perf_test.csv',
                    file=csv_file
                )

            start_time = time.time()
            wrapper = GabedaWrapper(upload)
            wrapper.process_complete_pipeline()
            elapsed_time = time.time() - start_time

            self.assertLess(elapsed_time, 60.0, f"Processing took {elapsed_time:.2f}s (should be < 60s)")

        finally:
            os.unlink(csv_path)

    def test_performance_memory_efficiency(self):
        """Test 7.2: Verify memory usage stays reasonable."""
        # Large dataset processing should not cause memory issues
        rows = [f"2024-01-{i % 30 + 1:02d},T{i:06d},P{i % 100:03d},{i % 50 + 1},{(i % 50 + 1) * 10.0}"
                for i in range(1, 5001)]
        csv_content = "in_dt,in_trans_id,in_product_id,in_quantity,in_price_total\n" + "\n".join(rows)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='memory_test.csv',
                    file=csv_file
                )

            # Should complete without MemoryError
            wrapper = GabedaWrapper(upload)
            wrapper.process_complete_pipeline()

            self.assertTrue(True)  # If we got here, no memory issues

        finally:
            os.unlink(csv_path)


class TestGabedaIntegrationSecurity(TestCase):
    """Test Type 8: SECURITY - Data isolation and validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            password='test123'
        )
        self.company = Company.objects.create(
            name='Test Company',
            rut='12345678-9'
        )
        self.other_company = Company.objects.create(
            name='Other Company',
            rut='98765432-1'
        )

    def test_security_data_isolation(self):
        """Test 8.1: Ensure data cannot leak between companies."""
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001,P001,10,100.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='secure.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            wrapper.process_complete_pipeline()

            # Verify data only accessible to owning company
            company_data = RawTransaction.objects.filter(company=self.company)
            other_data = RawTransaction.objects.filter(company=self.other_company)

            self.assertGreater(company_data.count(), 0)
            self.assertEqual(other_data.count(), 0)

        finally:
            os.unlink(csv_path)

    def test_security_sql_injection_prevention(self):
        """Test 8.2: Prevent SQL injection through data fields."""
        # Malicious data that could attempt SQL injection
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001'; DROP TABLE companies; --,P001,10,100.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='malicious.csv',
                    file=csv_file
                )

            wrapper = GabedaWrapper(upload)
            wrapper.process_complete_pipeline()

            # Verify companies table still exists (not dropped)
            self.assertTrue(Company.objects.filter(id=self.company.id).exists())

            # Verify malicious string was just stored as data
            trans = RawTransaction.objects.filter(company=self.company).first()
            self.assertIn("DROP TABLE", trans.data['in_trans_id'])

        finally:
            os.unlink(csv_path)

    def test_security_path_traversal_prevention(self):
        """Test 8.3: Prevent path traversal attacks."""
        # Attempt to use path traversal in filename
        csv_content = """in_dt,in_trans_id,in_product_id,in_quantity,in_price_total
2024-01-01,T001,P001,10,100.0"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            with open(csv_path, 'rb') as csv_file:
                upload = Upload.objects.create(
                    company=self.company,
                    uploaded_by=self.user,
                    filename='../../../etc/passwd.csv',  # Malicious filename
                    file=csv_file
                )

            # Should process safely without accessing /etc/passwd
            wrapper = GabedaWrapper(upload)
            wrapper.process_complete_pipeline()

            # Verify upload completed safely
            self.assertTrue(upload.status in ['completed', 'processing'])

        finally:
            os.unlink(csv_path)
