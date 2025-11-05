"""
Comprehensive tests for authentication models.

Tests cover all 8 required types:
1. valid - Happy path scenarios
2. error - Error handling
3. invalid - Input validation
4. edge - Boundary conditions
5. functional - Business logic
6. visual - N/A for backend models
7. performance - Query performance
8. security - Security validation
"""

import pytest
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from datetime import timedelta
from .models import User, PasswordResetToken, EmailVerificationToken


class UserModelTests(TestCase):
    """Tests for User model covering all 8 test types."""

    def setUp(self):
        """Set up test data."""
        self.user_data = {
            'email': 'test@ayni.cl',
            'username': 'testuser',
            'password': 'TestPass123!',
        }

    # TEST TYPE 1: VALID (Happy Path)
    def test_valid_user_creation(self):
        """Test creating a user with valid data."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(user.email, 'test@ayni.cl')
        self.assertTrue(user.check_password('TestPass123!'))
        self.assertFalse(user.is_email_verified)
        self.assertEqual(user.failed_login_attempts, 0)

    def test_valid_user_string_representation(self):
        """Test user __str__ method."""
        user = User.objects.create_user(**self.user_data)
        expected = f"{user.email} ({user.username})"
        self.assertEqual(str(user), expected)

    # TEST TYPE 2: ERROR (Error Handling)
    def test_error_duplicate_email(self):
        """Test error handling for duplicate email."""
        User.objects.create_user(**self.user_data)
        with self.assertRaises(IntegrityError):
            User.objects.create_user(**self.user_data)

    def test_error_missing_required_fields(self):
        """Test error when required fields are missing."""
        with self.assertRaises(TypeError):
            User.objects.create_user(email='test2@ayni.cl')

    # TEST TYPE 3: INVALID (Input Validation)
    def test_invalid_email_format(self):
        """Test validation rejects invalid email formats."""
        user = User(
            email='invalid-email',
            username='testuser2'
        )
        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_invalid_empty_email(self):
        """Test validation rejects empty email."""
        user = User(
            email='',
            username='testuser3'
        )
        with self.assertRaises(ValidationError):
            user.full_clean()

    # TEST TYPE 4: EDGE (Boundary Conditions)
    def test_edge_maximum_failed_login_attempts(self):
        """Test lockout after maximum failed attempts."""
        user = User.objects.create_user(**self.user_data)

        # Simulate 5 failed attempts
        for i in range(5):
            user.increment_failed_attempts()

        user.refresh_from_db()
        self.assertEqual(user.failed_login_attempts, 5)
        self.assertTrue(user.is_locked_out())
        self.assertIsNotNone(user.lockout_until)

    def test_edge_lockout_expiration(self):
        """Test lockout expires after timeout."""
        user = User.objects.create_user(**self.user_data)

        # Set lockout in the past
        user.lockout_until = timezone.now() - timedelta(minutes=1)
        user.save()

        self.assertFalse(user.is_locked_out())

    def test_edge_very_long_email(self):
        """Test handling of very long (but valid) email."""
        long_email = 'a' * 50 + '@' + 'b' * 50 + '.com'
        user = User.objects.create_user(
            email=long_email,
            username='longuser',
            password='TestPass123!'
        )
        self.assertEqual(user.email, long_email)

    # TEST TYPE 5: FUNCTIONAL (Business Logic)
    def test_functional_reset_failed_attempts(self):
        """Test resetting failed login attempts."""
        user = User.objects.create_user(**self.user_data)

        # Increment attempts
        user.increment_failed_attempts()
        user.increment_failed_attempts()
        self.assertEqual(user.failed_login_attempts, 2)

        # Reset
        user.reset_failed_attempts()
        user.refresh_from_db()
        self.assertEqual(user.failed_login_attempts, 0)
        self.assertIsNone(user.lockout_until)

    def test_functional_password_hashing(self):
        """Test passwords are properly hashed."""
        user = User.objects.create_user(**self.user_data)

        # Password should not be stored in plaintext
        self.assertNotEqual(user.password, 'TestPass123!')
        # But should be verifiable
        self.assertTrue(user.check_password('TestPass123!'))
        self.assertFalse(user.check_password('WrongPassword'))

    def test_functional_email_verification_workflow(self):
        """Test email verification status changes."""
        user = User.objects.create_user(**self.user_data)

        self.assertFalse(user.is_email_verified)

        user.is_email_verified = True
        user.save()

        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)

    # TEST TYPE 6: VISUAL (N/A for backend models)
    # Skipped - no visual component in backend models

    # TEST TYPE 7: PERFORMANCE
    def test_performance_bulk_user_creation(self):
        """Test performance of creating multiple users."""
        import time

        start_time = time.time()

        users = [
            User(
                email=f'user{i}@ayni.cl',
                username=f'user{i}'
            )
            for i in range(100)
        ]
        User.objects.bulk_create(users)

        duration = time.time() - start_time

        # Should create 100 users in less than 1 second
        self.assertLess(duration, 1.0)
        self.assertEqual(User.objects.count(), 100)

    def test_performance_user_lookup_by_email(self):
        """Test query performance for email lookup."""
        # Create users
        for i in range(50):
            User.objects.create_user(
                email=f'user{i}@ayni.cl',
                username=f'user{i}',
                password='TestPass123!'
            )

        import time
        start_time = time.time()

        user = User.objects.get(email='user25@ayni.cl')

        duration = time.time() - start_time

        # Lookup should be fast due to index
        self.assertLess(duration, 0.1)
        self.assertEqual(user.username, 'user25')

    # TEST TYPE 8: SECURITY
    def test_security_password_not_logged(self):
        """Test password is not exposed in string representation."""
        user = User.objects.create_user(**self.user_data)

        user_str = str(user)
        self.assertNotIn('TestPass123!', user_str)
        self.assertNotIn(user.password, user_str)

    def test_security_failed_login_tracking(self):
        """Test failed login attempts are tracked for security."""
        user = User.objects.create_user(**self.user_data)

        self.assertEqual(user.failed_login_attempts, 0)

        user.increment_failed_attempts()
        user.refresh_from_db()

        self.assertEqual(user.failed_login_attempts, 1)

    def test_security_lockout_after_brute_force(self):
        """Test account locks after brute force attempts."""
        user = User.objects.create_user(**self.user_data)

        # Simulate brute force attack
        for i in range(5):
            user.increment_failed_attempts()

        user.refresh_from_db()

        # Account should be locked
        self.assertTrue(user.is_locked_out())
        self.assertIsNotNone(user.lockout_until)

        # Lockout should be at least 10 minutes
        time_until_unlock = user.lockout_until - timezone.now()
        self.assertGreater(time_until_unlock.total_seconds(), 600)


class PasswordResetTokenTests(TestCase):
    """Tests for PasswordResetToken model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            username='testuser',
            password='TestPass123!'
        )

    # TEST TYPE 1: VALID
    def test_valid_token_creation(self):
        """Test creating a password reset token."""
        token = PasswordResetToken.objects.create(
            user=self.user,
            token='test-token-123',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        self.assertFalse(token.used)
        self.assertTrue(token.is_valid())

    # TEST TYPE 2: ERROR
    def test_error_duplicate_token(self):
        """Test error on duplicate token."""
        PasswordResetToken.objects.create(
            user=self.user,
            token='unique-token',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        with self.assertRaises(IntegrityError):
            PasswordResetToken.objects.create(
                user=self.user,
                token='unique-token',
                expires_at=timezone.now() + timedelta(hours=1)
            )

    # TEST TYPE 4: EDGE
    def test_edge_expired_token(self):
        """Test expired token is not valid."""
        token = PasswordResetToken.objects.create(
            user=self.user,
            token='expired-token',
            expires_at=timezone.now() - timedelta(hours=1)
        )
        self.assertFalse(token.is_valid())

    def test_edge_used_token(self):
        """Test used token is not valid."""
        token = PasswordResetToken.objects.create(
            user=self.user,
            token='used-token',
            expires_at=timezone.now() + timedelta(hours=1),
            used=True
        )
        self.assertFalse(token.is_valid())

    # TEST TYPE 5: FUNCTIONAL
    def test_functional_token_expiration_workflow(self):
        """Test complete token expiration workflow."""
        # Create valid token
        token = PasswordResetToken.objects.create(
            user=self.user,
            token='workflow-token',
            expires_at=timezone.now() + timedelta(hours=1)
        )

        # Should be valid initially
        self.assertTrue(token.is_valid())

        # Mark as used
        token.used = True
        token.save()

        # Should no longer be valid
        self.assertFalse(token.is_valid())

    # TEST TYPE 8: SECURITY
    def test_security_token_cannot_be_reused(self):
        """Test security: tokens cannot be reused."""
        token = PasswordResetToken.objects.create(
            user=self.user,
            token='one-time-token',
            expires_at=timezone.now() + timedelta(hours=1)
        )

        # Use the token
        self.assertTrue(token.is_valid())
        token.used = True
        token.save()

        # Should not be valid anymore
        self.assertFalse(token.is_valid())


class EmailVerificationTokenTests(TestCase):
    """Tests for EmailVerificationToken model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@ayni.cl',
            username='testuser',
            password='TestPass123!'
        )

    # TEST TYPE 1: VALID
    def test_valid_email_verification_token(self):
        """Test creating an email verification token."""
        token = EmailVerificationToken.objects.create(
            user=self.user,
            token='verify-token-123',
            expires_at=timezone.now() + timedelta(days=1)
        )
        self.assertFalse(token.verified)
        self.assertTrue(token.is_valid())

    # TEST TYPE 5: FUNCTIONAL
    def test_functional_email_verification_workflow(self):
        """Test complete email verification workflow."""
        # User starts unverified
        self.assertFalse(self.user.is_email_verified)

        # Create verification token
        token = EmailVerificationToken.objects.create(
            user=self.user,
            token='verify-workflow',
            expires_at=timezone.now() + timedelta(days=1)
        )

        # Token should be valid
        self.assertTrue(token.is_valid())

        # Verify token
        token.verified = True
        token.save()

        # Mark user as verified
        self.user.is_email_verified = True
        self.user.save()

        # Token should no longer be valid
        self.assertFalse(token.is_valid())

        # User should be verified
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)

    # TEST TYPE 8: SECURITY
    def test_security_verification_token_expires(self):
        """Test security: verification tokens expire."""
        token = EmailVerificationToken.objects.create(
            user=self.user,
            token='expiring-token',
            expires_at=timezone.now() + timedelta(seconds=1)
        )

        self.assertTrue(token.is_valid())

        # Simulate time passage
        token.expires_at = timezone.now() - timedelta(seconds=1)
        token.save()

        self.assertFalse(token.is_valid())
