"""
Comprehensive API tests for company management endpoints.

Tests cover all 8 required types:
1. valid - Happy path scenarios
2. error - Error handling
3. invalid - Input validation
4. edge - Boundary conditions
5. functional - Business logic
6. visual - N/A for backend
7. performance - Response times
8. security - Authentication, authorization, data isolation
"""

import time
import pytest
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.authentication.models import User
from .models import Company, UserCompany


class CompanyAPITests(TestCase):
    """Tests for Company management API endpoints."""

    def setUp(self):
        """Set up test data and API client."""
        self.client = APIClient()

        # Create test users
        self.user1 = User.objects.create_user(
            email='user1@test.com',
            username='user1',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            email='user2@test.com',
            username='user2',
            password='testpass123'
        )

        # Valid company data
        self.valid_company_data = {
            'name': 'Test PYME',
            'rut': '12.345.678-9',
            'industry': 'retail',
            'size': 'micro',
        }

    def get_auth_token(self, user):
        """Helper to get JWT token for user."""
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)

    # ============================================================================
    # TEST TYPE 1: VALID (Happy Path)
    # ============================================================================

    def test_valid_create_company(self):
        """Test creating a company with valid data."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.post('/api/companies/', self.valid_company_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Test PYME')
        self.assertEqual(response.data['rut'], '12.345.678-9')

        # Verify UserCompany relationship created with owner role
        company_id = response.data['id']
        user_company = UserCompany.objects.get(company_id=company_id, user=self.user1)
        self.assertEqual(user_company.role, 'owner')

    def test_valid_list_companies(self):
        """Test listing companies for authenticated user."""
        # Create company
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(
            user=self.user1,
            company=company,
            role='owner'
        )

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get('/api/companies/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Test PYME')

    def test_valid_get_company_details(self):
        """Test retrieving specific company details."""
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(user=self.user1, company=company, role='owner')

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get(f'/api/companies/{company.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test PYME')
        self.assertEqual(response.data['user_role'], 'owner')

    def test_valid_update_company(self):
        """Test updating company details."""
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(user=self.user1, company=company, role='owner')

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        update_data = {'name': 'Updated PYME Name'}
        response = self.client.patch(f'/api/companies/{company.id}/', update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated PYME Name')

        # Verify database updated
        company.refresh_from_db()
        self.assertEqual(company.name, 'Updated PYME Name')

    def test_valid_soft_delete_company(self):
        """Test soft deleting a company."""
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(user=self.user1, company=company, role='owner')

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.delete(f'/api/companies/{company.id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify soft delete (not hard delete)
        company.refresh_from_db()
        self.assertFalse(company.is_active)

    def test_valid_list_company_users(self):
        """Test listing all users for a company."""
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(user=self.user1, company=company, role='owner')
        UserCompany.objects.create(user=self.user2, company=company, role='viewer')

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get(f'/api/companies/{company.id}/users/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    # ============================================================================
    # TEST TYPE 2: ERROR (Error Handling)
    # ============================================================================

    def test_error_duplicate_rut(self):
        """Test handling duplicate RUT error."""
        Company.objects.create(**self.valid_company_data)

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.post('/api/companies/', self.valid_company_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rut', response.data)

    def test_error_company_not_found(self):
        """Test handling company not found error."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get('/api/companies/99999/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_error_invalid_industry_code(self):
        """Test handling invalid industry code."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        invalid_data = self.valid_company_data.copy()
        invalid_data['industry'] = 'invalid_industry'

        response = self.client.post('/api/companies/', invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('industry', response.data)

    # ============================================================================
    # TEST TYPE 3: INVALID (Input Validation)
    # ============================================================================

    def test_invalid_rut_format(self):
        """Test rejection of invalid RUT format."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        invalid_data = self.valid_company_data.copy()
        invalid_data['rut'] = '12345678'  # Missing format

        response = self.client.post('/api/companies/', invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_rut_check_digit(self):
        """Test rejection of invalid RUT check digit."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        invalid_data = self.valid_company_data.copy()
        invalid_data['rut'] = '12.345.678-0'  # Wrong check digit

        response = self.client.post('/api/companies/', invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rut', response.data)

    def test_invalid_empty_company_name(self):
        """Test rejection of empty company name."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        invalid_data = self.valid_company_data.copy()
        invalid_data['name'] = ''

        response = self.client.post('/api/companies/', invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)

    def test_invalid_company_name_too_short(self):
        """Test rejection of too-short company name."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        invalid_data = self.valid_company_data.copy()
        invalid_data['name'] = 'A'  # Only 1 character

        response = self.client.post('/api/companies/', invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_size_choice(self):
        """Test rejection of invalid size choice."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        invalid_data = self.valid_company_data.copy()
        invalid_data['size'] = 'mega'  # Not a valid choice

        response = self.client.post('/api/companies/', invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ============================================================================
    # TEST TYPE 4: EDGE (Edge Cases)
    # ============================================================================

    def test_edge_user_with_no_companies(self):
        """Test user with no companies gets empty list."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get('/api/companies/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_edge_user_with_50_companies(self):
        """Test user with many companies (50+)."""
        # Create 50 companies
        for i in range(50):
            company = Company.objects.create(
                name=f'Company {i}',
                rut=f'{i+10}.000.000-{(i % 10)}',
                industry='retail',
                size='micro'
            )
            UserCompany.objects.create(user=self.user1, company=company, role='viewer')

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get('/api/companies/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 50)

    def test_edge_soft_deleted_companies_not_listed(self):
        """Test that soft-deleted companies don't appear in listings."""
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(user=self.user1, company=company, role='owner')

        # Soft delete
        company.soft_delete()

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get('/api/companies/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_edge_company_name_with_special_characters(self):
        """Test company name with special characters."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        special_data = self.valid_company_data.copy()
        special_data['name'] = 'Café & Té S.A.'
        special_data['rut'] = '76.123.456-7'

        response = self.client.post('/api/companies/', special_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Café & Té S.A.')

    # ============================================================================
    # TEST TYPE 5: FUNCTIONAL (Business Logic)
    # ============================================================================

    def test_functional_soft_delete_preserves_data(self):
        """Test that soft delete preserves company data."""
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(user=self.user1, company=company, role='owner')

        company_id = company.id
        original_name = company.name

        # Soft delete
        company.soft_delete()

        # Verify data still exists
        deleted_company = Company.objects.get(id=company_id)
        self.assertEqual(deleted_company.name, original_name)
        self.assertFalse(deleted_company.is_active)

    def test_functional_user_company_permissions(self):
        """Test that user permissions work correctly."""
        company = Company.objects.create(**self.valid_company_data)
        user_company = UserCompany.objects.create(
            user=self.user1,
            company=company,
            role='viewer'
        )

        # Viewer should not have upload permission
        self.assertFalse(user_company.has_permission('can_upload'))

        # Owner should have all permissions
        user_company.role = 'owner'
        self.assertTrue(user_company.has_permission('can_upload'))
        self.assertTrue(user_company.has_permission('can_manage_company'))

    def test_functional_cannot_delete_last_owner(self):
        """Test that system prevents deleting the last owner."""
        company = Company.objects.create(**self.valid_company_data)
        user_company = UserCompany.objects.create(user=self.user1, company=company, role='owner')

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        # Try to remove the only owner
        response = self.client.delete(f'/api/companies/user-companies/{user_company.id}/')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('last owner', response.data['error'])

    def test_functional_role_based_permissions(self):
        """Test role-based permission enforcement."""
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(user=self.user1, company=company, role='viewer')

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        # Viewer should not be able to update company
        update_data = {'name': 'Hacked Name'}
        response = self.client.patch(f'/api/companies/{company.id}/', update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ============================================================================
    # TEST TYPE 6: VISUAL (N/A for Backend)
    # ============================================================================
    # Visual tests not applicable for backend APIs

    # ============================================================================
    # TEST TYPE 7: PERFORMANCE (Response Times)
    # ============================================================================

    def test_performance_company_list_query(self):
        """Test company list query completes quickly (< 100ms)."""
        # Create multiple companies
        for i in range(10):
            company = Company.objects.create(
                name=f'Company {i}',
                rut=f'{i+10}.000.000-{(i % 10)}',
                industry='retail',
                size='micro'
            )
            UserCompany.objects.create(user=self.user1, company=company, role='viewer')

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        start_time = time.time()
        response = self.client.get('/api/companies/')
        duration_ms = (time.time() - start_time) * 1000

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(duration_ms, 100, f"Query took {duration_ms}ms, expected < 100ms")

    def test_performance_company_creation(self):
        """Test company creation completes quickly."""
        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        start_time = time.time()
        response = self.client.post('/api/companies/', self.valid_company_data, format='json')
        duration_ms = (time.time() - start_time) * 1000

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertLess(duration_ms, 200, f"Creation took {duration_ms}ms, expected < 200ms")

    # ============================================================================
    # TEST TYPE 8: SECURITY (Authentication, Authorization, Data Isolation)
    # ============================================================================

    def test_security_unauthenticated_access_denied(self):
        """Test that unauthenticated requests are rejected."""
        response = self.client.get('/api/companies/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_security_users_cannot_access_other_users_companies(self):
        """Test data isolation between users."""
        # User1 creates company
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(user=self.user1, company=company, role='owner')

        # User2 tries to access
        token = self.get_auth_token(self.user2)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get(f'/api/companies/{company.id}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_security_users_cannot_modify_other_users_companies(self):
        """Test that users cannot modify companies they don't have access to."""
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(user=self.user1, company=company, role='owner')

        # User2 tries to update
        token = self.get_auth_token(self.user2)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        update_data = {'name': 'Hacked Name'}
        response = self.client.patch(f'/api/companies/{company.id}/', update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify company not modified
        company.refresh_from_db()
        self.assertEqual(company.name, 'Test PYME')

    def test_security_only_owner_can_delete_company(self):
        """Test that only owners can delete companies."""
        company = Company.objects.create(**self.valid_company_data)
        UserCompany.objects.create(user=self.user1, company=company, role='admin')  # Admin, not owner

        token = self.get_auth_token(self.user1)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.delete(f'/api/companies/{company.id}/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Verify company not deleted
        company.refresh_from_db()
        self.assertTrue(company.is_active)

    def test_security_jwt_token_required(self):
        """Test that JWT token is required for all endpoints."""
        endpoints = [
            '/api/companies/',
            f'/api/companies/1/',
        ]

        for endpoint in endpoints:
            response = self.client.get(endpoint)
            self.assertIn(
                response.status_code,
                [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
                f"Endpoint {endpoint} should require authentication"
            )

    def test_security_invalid_token_rejected(self):
        """Test that invalid JWT tokens are rejected."""
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid_token_here')

        response = self.client.get('/api/companies/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
