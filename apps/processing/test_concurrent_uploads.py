"""
Tests for concurrent upload prevention (One Upload Per Company Rule).

This module tests the business rule that prevents a company from having
multiple uploads processing simultaneously. This ensures:
- Fair resource allocation across companies
- Maximum concurrent uploads = number of registered companies
- No single company can monopolize processing resources
"""

import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.processing.models import Upload

User = get_user_model()


class UploadConcurrencyTests(TestCase):
    """
    Test Type 4: EDGE CASES - Concurrent Upload Prevention

    Tests the business rule: One upload per company at a time.
    """

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='test123'
        )
        self.company = Company.objects.create(
            name='Test Company',
            rut='12.345.678-9',
            industry='retail',
            size='micro'
        )
        UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role='owner'
        )
        self.client.force_authenticate(user=self.user)

    def _create_csv_file(self, filename='test.csv'):
        """Helper to create test CSV file."""
        content = "fecha,monto,producto\n2024-01-01,1000,Product A\n"
        return SimpleUploadedFile(
            filename,
            content.encode('utf-8'),
            content_type='text/csv'
        )

    def test_prevent_concurrent_uploads_same_company(self):
        """Test: Company cannot upload while another upload is in progress"""
        # Create first upload (active)
        upload1 = Upload.objects.create(
            company=self.company,
            user=self.user,
            filename='first.csv',
            file_path='/tmp/first.csv',
            file_size=1000,
            status='processing',  # Active status
            column_mappings={'fecha': 'date', 'monto': 'amount'}
        )

        # Attempt second upload (should fail)
        csv_file = self._create_csv_file('second.csv')
        response = self.client.post('/api/processing/uploads/', {
            'company': self.company.id,
            'file': csv_file,
            'column_mappings': json.dumps({'fecha': 'date', 'monto': 'amount'}),
        }, format='multipart')

        # Should return 409 Conflict
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('error', response.data)
        self.assertIn('Upload already in progress', response.data['error'])
        self.assertEqual(response.data['active_upload_id'], upload1.id)
        self.assertEqual(response.data['active_upload_status'], 'processing')

    def test_allow_upload_after_previous_completed(self):
        """Test: Company can upload after previous upload completes"""
        # Create first upload (completed)
        upload1 = Upload.objects.create(
            company=self.company,
            user=self.user,
            filename='first.csv',
            file_path='/tmp/first.csv',
            file_size=1000,
            status='completed',  # Not active
            column_mappings={'fecha': 'date', 'monto': 'amount'}
        )

        # Attempt second upload (should succeed)
        csv_file = self._create_csv_file('second.csv')
        response = self.client.post('/api/processing/uploads/', {
            'company': self.company.id,
            'file': csv_file,
            'column_mappings': json.dumps({'fecha': 'date', 'monto': 'amount'}),
        }, format='multipart')

        # Should succeed
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', response.data)

    def test_allow_upload_after_previous_failed(self):
        """Test: Company can upload after previous upload fails"""
        # Create first upload (failed)
        upload1 = Upload.objects.create(
            company=self.company,
            user=self.user,
            filename='first.csv',
            file_path='/tmp/first.csv',
            file_size=1000,
            status='failed',  # Not active
            error_message='Test error',
            column_mappings={'fecha': 'date', 'monto': 'amount'}
        )

        # Attempt second upload (should succeed)
        csv_file = self._create_csv_file('second.csv')
        response = self.client.post('/api/processing/uploads/', {
            'company': self.company.id,
            'file': csv_file,
            'column_mappings': json.dumps({'fecha': 'date', 'monto': 'amount'}),
        }, format='multipart')

        # Should succeed
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_different_companies_can_upload_simultaneously(self):
        """Test: Different companies can have concurrent uploads"""
        # Create second company
        user2 = User.objects.create_user(
            username='user2',
            email='user2@test.com',
            password='test123'
        )
        company2 = Company.objects.create(
            name='Company 2',
            rut='98.765.432-1',
            industry='technology',
            size='small'
        )
        UserCompany.objects.create(
            user=user2,
            company=company2,
            role='owner'
        )

        # Company 1 has active upload
        upload1 = Upload.objects.create(
            company=self.company,
            user=self.user,
            filename='company1.csv',
            file_path='/tmp/company1.csv',
            file_size=1000,
            status='processing',
            column_mappings={'fecha': 'date'}
        )

        # Company 2 should be able to upload (different company)
        self.client.force_authenticate(user=user2)
        csv_file = self._create_csv_file('company2.csv')
        response = self.client.post('/api/processing/uploads/', {
            'company': company2.id,
            'file': csv_file,
            'column_mappings': json.dumps({'fecha': 'date', 'monto': 'amount'}),
        }, format='multipart')

        # Should succeed
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Upload.objects.filter(status__in=['pending', 'validating', 'processing']).count(), 2)

    def test_has_active_upload_method(self):
        """Test: Upload.has_active_upload() method works correctly"""
        # No active uploads
        self.assertFalse(Upload.has_active_upload(self.company))

        # Create pending upload
        upload1 = Upload.objects.create(
            company=self.company,
            user=self.user,
            filename='test.csv',
            file_path='/tmp/test.csv',
            file_size=1000,
            status='pending'
        )
        self.assertTrue(Upload.has_active_upload(self.company))

        # Mark as completed
        upload1.status = 'completed'
        upload1.save()
        self.assertFalse(Upload.has_active_upload(self.company))

    def test_get_active_upload_method(self):
        """Test: Upload.get_active_upload() returns correct upload"""
        # No active upload
        self.assertIsNone(Upload.get_active_upload(self.company))

        # Create active upload
        upload = Upload.objects.create(
            company=self.company,
            user=self.user,
            filename='test.csv',
            file_path='/tmp/test.csv',
            file_size=1000,
            status='processing'
        )

        # Get active upload
        active = Upload.get_active_upload(self.company)
        self.assertIsNotNone(active)
        self.assertEqual(active.id, upload.id)

    def test_prevent_concurrent_validating_status(self):
        """Test: Prevent upload when another is in 'validating' status"""
        # Create upload in validating state
        upload1 = Upload.objects.create(
            company=self.company,
            user=self.user,
            filename='validating.csv',
            file_path='/tmp/validating.csv',
            file_size=1000,
            status='validating',
            column_mappings={'fecha': 'date'}
        )

        # Attempt second upload
        csv_file = self._create_csv_file('second.csv')
        response = self.client.post('/api/processing/uploads/', {
            'company': self.company.id,
            'file': csv_file,
            'column_mappings': json.dumps({'fecha': 'date', 'monto': 'amount'}),
        }, format='multipart')

        # Should be rejected
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['active_upload_status'], 'validating')

    def test_response_includes_active_upload_details(self):
        """Test: 409 response includes details about active upload"""
        # Create active upload
        upload = Upload.objects.create(
            company=self.company,
            user=self.user,
            filename='active.csv',
            file_path='/tmp/active.csv',
            file_size=1000,
            status='processing',
            progress_percentage=45,
            column_mappings={'fecha': 'date'}
        )

        # Attempt second upload
        csv_file = self._create_csv_file('blocked.csv')
        response = self.client.post('/api/processing/uploads/', {
            'company': self.company.id,
            'file': csv_file,
            'column_mappings': json.dumps({'fecha': 'date'}),
        }, format='multipart')

        # Verify response includes all details
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['active_upload_id'], upload.id)
        self.assertEqual(response.data['active_upload_status'], 'processing')
        self.assertEqual(response.data['active_upload_progress'], 45)
        self.assertEqual(response.data['active_upload_filename'], 'active.csv')
        self.assertIn('detail', response.data)

    def test_allow_upload_after_previous_cancelled(self):
        """Test: Company can upload after previous upload is cancelled"""
        # Create cancelled upload
        upload1 = Upload.objects.create(
            company=self.company,
            user=self.user,
            filename='cancelled.csv',
            file_path='/tmp/cancelled.csv',
            file_size=1000,
            status='cancelled',  # Not active
            column_mappings={'fecha': 'date'}
        )

        # Attempt second upload (should succeed)
        csv_file = self._create_csv_file('new.csv')
        response = self.client.post('/api/processing/uploads/', {
            'company': self.company.id,
            'file': csv_file,
            'column_mappings': json.dumps({'fecha': 'date'}),
        }, format='multipart')

        # Should succeed
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
