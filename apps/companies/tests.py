"""
Comprehensive tests for company models.

Tests cover all 8 required types:
1. valid - Happy path scenarios
2. error - Error handling
3. invalid - Input validation
4. edge - Boundary conditions
5. functional - Business logic
6. visual - N/A for backend models
7. performance - Query performance
8. security - Security validation (data isolation)
"""

import pytest
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from apps.authentication.models import User
from .models import Company, UserCompany


class CompanyModelTests(TestCase):
    """Tests for Company model covering all 8 test types."""

    def setUp(self):
        """Set up test data."""
        self.company_data = {
            'name': 'Test PYME',
            'rut': '12.345.678-9',
            'industry': 'retail',
            'size': 'micro',
        }

    # TEST TYPE 1: VALID (Happy Path)
    def test_valid_company_creation(self):
        """Test creating a company with valid data."""
        company = Company.objects.create(**self.company_data)
        self.assertEqual(company.name, 'Test PYME')
        self.assertEqual(company.rut, '12.345.678-9')
        self.assertTrue(company.is_active)

    def test_valid_company_string_representation(self):
        """Test company __str__ method."""
        company = Company.objects.create(**self.company_data)
        expected = f"{company.name} ({company.rut})"
        self.assertEqual(str(company), expected)

    def test_valid_all_industry_types(self):
        """Test creating companies in all industry categories."""
        industries = ['retail', 'food', 'manufacturing', 'services',
                     'technology', 'construction', 'agriculture',
                     'healthcare', 'education', 'other']

        for i, industry in enumerate(industries):
            company = Company.objects.create(
                name=f'Company {i}',
                rut=f'{i+10}.000.000-0',
                industry=industry
            )
            self.assertEqual(company.industry, industry)

    # TEST TYPE 2: ERROR (Error Handling)
    def test_error_duplicate_rut(self):
        """Test error handling for duplicate RUT."""
        Company.objects.create(**self.company_data)
        with self.assertRaises(IntegrityError):
            Company.objects.create(**self.company_data)

    def test_error_missing_required_fields(self):
        """Test error when required fields are missing."""
        with self.assertRaises(IntegrityError):
            Company.objects.create(name='Test Company')

    # TEST TYPE 3: INVALID (Input Validation)
    def test_invalid_rut_format(self):
        """Test validation rejects invalid RUT formats."""
        company = Company(
            name='Invalid Company',
            rut='12345678-9',  # Missing dots
            industry='retail'
        )
        with self.assertRaises(ValidationError):
            company.full_clean()

    def test_invalid_rut_format_variations(self):
        """Test various invalid RUT formats are rejected."""
        invalid_ruts = [
            '123456789',  # No separator
            '12-345-678-9',  # Wrong separator
            '12.345.6789',  # Missing check digit
            'AA.BBB.CCC-D',  # Letters
        ]

        for invalid_rut in invalid_ruts:
            company = Company(
                name='Test',
                rut=invalid_rut,
                industry='retail'
            )
            with self.assertRaises(ValidationError):
                company.full_clean()

    # TEST TYPE 4: EDGE (Boundary Conditions)
    def test_edge_minimum_rut(self):
        """Test minimum valid RUT (1.000.000-0)."""
        company = Company.objects.create(
            name='Min RUT Company',
            rut='1.000.000-0',
            industry='retail'
        )
        self.assertEqual(company.rut, '1.000.000-0')

    def test_edge_maximum_rut(self):
        """Test maximum valid RUT (99.999.999-K)."""
        company = Company.objects.create(
            name='Max RUT Company',
            rut='99.999.999-K',
            industry='retail'
        )
        self.assertEqual(company.rut, '99.999.999-K')

    def test_edge_very_long_company_name(self):
        """Test handling of very long company name."""
        long_name = 'A' * 255  # Maximum CharField length
        company = Company.objects.create(
            name=long_name,
            rut='11.111.111-1',
            industry='retail'
        )
        self.assertEqual(len(company.name), 255)

    # TEST TYPE 5: FUNCTIONAL (Business Logic)
    def test_functional_soft_delete(self):
        """Test soft delete functionality."""
        company = Company.objects.create(**self.company_data)

        self.assertTrue(company.is_active)

        # Soft delete
        company.soft_delete()

        # Company should still exist but marked inactive
        company.refresh_from_db()
        self.assertFalse(company.is_active)

        # Should still be retrievable
        self.assertEqual(Company.objects.filter(pk=company.pk).count(), 1)

    def test_functional_company_user_relationship(self):
        """Test many-to-many relationship between companies and users."""
        company = Company.objects.create(**self.company_data)
        user = User.objects.create_user(
            email='test@ayni.cl',
            username='testuser',
            password='TestPass123!'
        )

        # Create relationship
        UserCompany.objects.create(
            user=user,
            company=company,
            role='owner'
        )

        # Test relationship
        self.assertIn(user, company.users.all())
        self.assertIn(company, user.companies.all())

    def test_functional_industry_choices(self):
        """Test all industry choices are valid."""
        valid_industries = [choice[0] for choice in Company.INDUSTRY_CHOICES]

        for industry in valid_industries:
            company = Company(
                name=f'Company {industry}',
                rut=f'{len(industry)}.111.111-1',
                industry=industry
            )
            # Should not raise validation error
            company.full_clean()

    # TEST TYPE 6: VISUAL (N/A for backend models)
    # Skipped - no visual component in backend models

    # TEST TYPE 7: PERFORMANCE
    def test_performance_bulk_company_creation(self):
        """Test performance of creating multiple companies."""
        import time

        start_time = time.time()

        companies = [
            Company(
                name=f'Company {i}',
                rut=f'{i+10}.000.{i:03d}-0',
                industry='retail',
                size='micro'
            )
            for i in range(100)
        ]
        Company.objects.bulk_create(companies)

        duration = time.time() - start_time

        # Should create 100 companies in less than 1 second
        self.assertLess(duration, 1.0)
        self.assertEqual(Company.objects.count(), 100)

    def test_performance_company_lookup_by_rut(self):
        """Test query performance for RUT lookup."""
        # Create companies
        for i in range(50):
            Company.objects.create(
                name=f'Company {i}',
                rut=f'{i+10}.000.000-0',
                industry='retail'
            )

        import time
        start_time = time.time()

        company = Company.objects.get(rut='35.000.000-0')

        duration = time.time() - start_time

        # Lookup should be fast due to unique index
        self.assertLess(duration, 0.1)
        self.assertEqual(company.name, 'Company 25')

    # TEST TYPE 8: SECURITY
    def test_security_rut_uniqueness_enforced(self):
        """Test security: RUT uniqueness prevents identity conflicts."""
        Company.objects.create(**self.company_data)

        # Attempting to create another company with same RUT should fail
        with self.assertRaises(IntegrityError):
            Company.objects.create(
                name='Different Name',
                rut='12.345.678-9',  # Same RUT
                industry='technology'
            )

    def test_security_soft_delete_preserves_data(self):
        """Test security: soft delete preserves data for audit."""
        company = Company.objects.create(**self.company_data)
        original_name = company.name

        company.soft_delete()

        # Data should be preserved
        company.refresh_from_db()
        self.assertEqual(company.name, original_name)
        self.assertFalse(company.is_active)


class UserCompanyTests(TestCase):
    """Tests for UserCompany relationship model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            username='testuser',
            password='TestPass123!'
        )
        self.company = Company.objects.create(
            name='Test Company',
            rut='12.345.678-9',
            industry='retail'
        )

    # TEST TYPE 1: VALID
    def test_valid_user_company_creation(self):
        """Test creating user-company relationship."""
        uc = UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role='owner'
        )
        self.assertEqual(uc.role, 'owner')
        self.assertTrue(uc.is_active)

    def test_valid_all_role_types(self):
        """Test all role types can be assigned."""
        roles = ['owner', 'admin', 'manager', 'analyst', 'viewer']

        for i, role in enumerate(roles):
            user = User.objects.create_user(
                email=f'user{i}@ayni.cl',
                username=f'user{i}',
                password='TestPass123!'
            )
            uc = UserCompany.objects.create(
                user=user,
                company=self.company,
                role=role
            )
            self.assertEqual(uc.role, role)

    # TEST TYPE 2: ERROR
    def test_error_duplicate_user_company(self):
        """Test error on duplicate user-company relationship."""
        UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role='owner'
        )

        with self.assertRaises(IntegrityError):
            UserCompany.objects.create(
                user=self.user,
                company=self.company,
                role='admin'
            )

    # TEST TYPE 4: EDGE
    def test_edge_user_multiple_companies(self):
        """Test user can belong to multiple companies."""
        company2 = Company.objects.create(
            name='Company 2',
            rut='98.765.432-1',
            industry='technology'
        )

        UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role='owner'
        )
        UserCompany.objects.create(
            user=self.user,
            company=company2,
            role='viewer'
        )

        self.assertEqual(self.user.companies.count(), 2)

    def test_edge_company_multiple_users(self):
        """Test company can have multiple users."""
        user2 = User.objects.create_user(
            email='user2@ayni.cl',
            username='user2',
            password='TestPass123!'
        )

        UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role='owner'
        )
        UserCompany.objects.create(
            user=user2,
            company=self.company,
            role='admin'
        )

        self.assertEqual(self.company.users.count(), 2)

    # TEST TYPE 5: FUNCTIONAL
    def test_functional_default_permissions(self):
        """Test default permissions are set correctly for each role."""
        roles = ['owner', 'admin', 'manager', 'analyst', 'viewer']

        for role in roles:
            permissions = UserCompany.get_default_permissions(role)

            # All roles should have view permission
            self.assertTrue(permissions['can_view'])

            # Only owner and admin can manage users
            if role in ['owner', 'admin']:
                self.assertTrue(permissions['can_manage_users'])
            else:
                self.assertFalse(permissions['can_manage_users'])

    def test_functional_has_permission_method(self):
        """Test has_permission method works correctly."""
        uc = UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role='viewer',
            permissions={'can_view': True, 'can_export': False}
        )

        self.assertTrue(uc.has_permission('can_view'))
        self.assertFalse(uc.has_permission('can_export'))

    def test_functional_owner_has_all_permissions(self):
        """Test owner role has all permissions."""
        uc = UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role='owner'
        )

        # Owner should have all permissions regardless of permissions field
        self.assertTrue(uc.has_permission('can_view'))
        self.assertTrue(uc.has_permission('can_upload'))
        self.assertTrue(uc.has_permission('can_delete_data'))
        self.assertTrue(uc.has_permission('can_manage_company'))

    # TEST TYPE 8: SECURITY
    def test_security_permission_isolation(self):
        """Test security: permissions are isolated per company."""
        company2 = Company.objects.create(
            name='Company 2',
            rut='98.765.432-1',
            industry='technology'
        )

        # User is owner of company1
        uc1 = UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role='owner'
        )

        # User is viewer of company2
        uc2 = UserCompany.objects.create(
            user=self.user,
            company=company2,
            role='viewer'
        )

        # Permissions should be different
        self.assertTrue(uc1.has_permission('can_manage_users'))
        self.assertFalse(uc2.has_permission('can_manage_users'))

    def test_security_inactive_relationship_preserved(self):
        """Test security: inactive relationships are preserved for audit."""
        uc = UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role='owner'
        )

        # Deactivate relationship
        uc.is_active = False
        uc.save()

        # Relationship should still exist
        self.assertEqual(
            UserCompany.objects.filter(user=self.user, company=self.company).count(),
            1
        )
