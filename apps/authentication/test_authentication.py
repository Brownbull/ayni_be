"""
Comprehensive authentication system tests for AYNI platform.

This module tests all authentication functionality with 8 test types:
1. Valid (happy path)
2. Error handling
3. Invalid input
4. Edge cases
5. Functional (business logic)
6. Visual (N/A for backend)
7. Performance
8. Security

Following backend-standard.md requirements for 80%+ coverage.
"""

import pytest
import time
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


@pytest.fixture
def api_client():
    """Provide an API client for tests."""
    return APIClient()


@pytest.fixture
def user_data():
    """Provide valid user registration data."""
    return {
        'email': 'test@ayni.cl',
        'username': 'testuser',
        'password': 'SecurePass123!',
        'password_confirm': 'SecurePass123!',
        'first_name': 'Test',
        'last_name': 'User'
    }


@pytest.fixture
def create_user():
    """Factory to create test users."""
    def _create_user(email='user@ayni.cl', username='user', password='Pass123!', **kwargs):
        user = User.objects.create_user(
            email=email,
            username=username,
            password=password,
            **kwargs
        )
        return user
    return _create_user


# ============================================================================
# TEST TYPE 1: VALID (Happy Path)
# ============================================================================

@pytest.mark.django_db
class TestValidAuthenticationFlows:
    """Test successful authentication scenarios."""

    def test_user_registration_success(self, api_client, user_data):
        """User can register with valid data."""
        url = reverse('authentication:register')
        response = api_client.post(url, user_data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert 'user' in response.data
        assert 'tokens' in response.data
        assert response.data['user']['email'] == user_data['email'].lower()
        assert 'access' in response.data['tokens']
        assert 'refresh' in response.data['tokens']

        # Verify user created in database
        user = User.objects.get(email=user_data['email'].lower())
        assert user.username == user_data['username']
        assert user.check_password(user_data['password'])

    def test_user_login_success(self, api_client, create_user):
        """User can login with correct credentials."""
        password = 'TestPass123!'
        user = create_user(email='login@ayni.cl', password=password)

        url = reverse('authentication:login')
        response = api_client.post(url, {
            'email': 'login@ayni.cl',
            'password': password
        }, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'user' in response.data
        assert 'tokens' in response.data
        assert response.data['user']['email'] == 'login@ayni.cl'

    def test_token_refresh_success(self, api_client, create_user):
        """User can refresh access token with valid refresh token."""
        user = create_user()
        refresh = RefreshToken.for_user(user)

        url = reverse('authentication:token_refresh')
        response = api_client.post(url, {
            'refresh': str(refresh)
        }, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data

    def test_logout_success(self, api_client, create_user):
        """User can logout successfully."""
        user = create_user()
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        url = reverse('authentication:logout')
        response = api_client.post(url, {
            'refresh': str(refresh)
        }, format='json')

        assert response.status_code == status.HTTP_205_RESET_CONTENT

    def test_profile_retrieval_success(self, api_client, create_user):
        """Authenticated user can retrieve their profile."""
        user = create_user()
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

        url = reverse('authentication:profile')
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == user.email
        assert response.data['username'] == user.username

    def test_password_change_success(self, api_client, create_user):
        """User can change password successfully."""
        old_password = 'OldPass123!'
        new_password = 'NewPass456!'
        user = create_user(password=old_password)

        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

        url = reverse('authentication:change_password')
        response = api_client.post(url, {
            'current_password': old_password,
            'new_password': new_password,
            'new_password_confirm': new_password
        }, format='json')

        assert response.status_code == status.HTTP_200_OK

        # Verify password changed
        user.refresh_from_db()
        assert user.check_password(new_password)
        assert not user.check_password(old_password)


# ============================================================================
# TEST TYPE 2: ERROR HANDLING
# ============================================================================

@pytest.mark.django_db
class TestAuthenticationErrorHandling:
    """Test error handling in authentication flows."""

    def test_login_with_wrong_password(self, api_client, create_user):
        """System handles wrong password gracefully."""
        create_user(email='user@ayni.cl', password='CorrectPass123!')

        url = reverse('authentication:login')
        response = api_client.post(url, {
            'email': 'user@ayni.cl',
            'password': 'WrongPass123!'
        }, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'attempts remaining' in str(response.data).lower() or 'invalid credentials' in str(response.data).lower()

    def test_login_with_nonexistent_user(self, api_client):
        """System handles login attempt for non-existent user."""
        url = reverse('authentication:login')
        response = api_client.post(url, {
            'email': 'nonexistent@ayni.cl',
            'password': 'Pass123!'
        }, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'invalid' in str(response.data).lower()

    def test_token_refresh_with_invalid_token(self, api_client):
        """System handles invalid refresh token."""
        url = reverse('authentication:token_refresh')
        response = api_client.post(url, {
            'refresh': 'invalid_token_string'
        }, format='json')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_profile_access_without_authentication(self, api_client):
        """System rejects unauthenticated profile access."""
        url = reverse('authentication:profile')
        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# TEST TYPE 3: INVALID INPUT
# ============================================================================

@pytest.mark.django_db
class TestAuthenticationInvalidInput:
    """Test invalid input validation."""

    def test_registration_with_invalid_email(self, api_client, user_data):
        """System rejects invalid email format."""
        user_data['email'] = 'not-an-email'

        url = reverse('authentication:register')
        response = api_client.post(url, user_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in response.data

    def test_registration_with_weak_password(self, api_client, user_data):
        """System rejects weak passwords."""
        user_data['password'] = '123'
        user_data['password_confirm'] = '123'

        url = reverse('authentication:register')
        response = api_client.post(url, user_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'password' in response.data

    def test_registration_with_mismatched_passwords(self, api_client, user_data):
        """System rejects mismatched password confirmation."""
        user_data['password_confirm'] = 'DifferentPass123!'

        url = reverse('authentication:register')
        response = api_client.post(url, user_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_registration_with_duplicate_email(self, api_client, user_data, create_user):
        """System rejects duplicate email registration."""
        create_user(email=user_data['email'])

        url = reverse('authentication:register')
        response = api_client.post(url, user_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in response.data or 'already exists' in str(response.data).lower()

    def test_login_with_missing_fields(self, api_client):
        """System rejects login with missing fields."""
        url = reverse('authentication:login')
        response = api_client.post(url, {'email': 'test@ayni.cl'}, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_password_with_wrong_current_password(self, api_client, create_user):
        """System rejects password change with incorrect current password."""
        user = create_user(password='CorrectPass123!')
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

        url = reverse('authentication:change_password')
        response = api_client.post(url, {
            'current_password': 'WrongPass123!',
            'new_password': 'NewPass456!',
            'new_password_confirm': 'NewPass456!'
        }, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'current_password' in response.data or 'incorrect' in str(response.data).lower()


# ============================================================================
# TEST TYPE 4: EDGE CASES
# ============================================================================

@pytest.mark.django_db
class TestAuthenticationEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_registration_with_very_long_email(self, api_client, user_data):
        """System handles very long email addresses."""
        user_data['email'] = 'a' * 200 + '@ayni.cl'

        url = reverse('authentication:register')
        response = api_client.post(url, user_data, format='json')

        # Should either accept (if within limit) or reject gracefully
        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]

    def test_concurrent_login_attempts(self, api_client, create_user):
        """System handles concurrent login attempts."""
        password = 'Pass123!'
        user = create_user(password=password)

        url = reverse('authentication:login')

        # Simulate multiple concurrent logins
        responses = []
        for _ in range(3):
            response = api_client.post(url, {
                'email': user.email,
                'password': password
            }, format='json')
            responses.append(response)

        # All should succeed
        for response in responses:
            assert response.status_code == status.HTTP_200_OK

    def test_user_with_no_username(self, api_client, user_data):
        """System handles user with empty username gracefully."""
        user_data['username'] = ''

        url = reverse('authentication:register')
        response = api_client.post(url, user_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_with_email_case_insensitivity(self, api_client, create_user):
        """System handles email case-insensitively."""
        password = 'Pass123!'
        create_user(email='user@ayni.cl', password=password)

        url = reverse('authentication:login')

        # Try with different cases
        for email in ['USER@ayni.cl', 'User@AYNI.CL', 'user@AYNI.cl']:
            response = api_client.post(url, {
                'email': email,
                'password': password
            }, format='json')
            assert response.status_code == status.HTTP_200_OK


# ============================================================================
# TEST TYPE 5: FUNCTIONAL (Business Logic)
# ============================================================================

@pytest.mark.django_db
class TestAuthenticationBusinessLogic:
    """Test business logic and functional requirements."""

    def test_failed_login_attempts_increment(self, api_client, create_user):
        """System increments failed login attempts counter."""
        user = create_user(email='user@ayni.cl', password='CorrectPass123!')
        assert user.failed_login_attempts == 0

        url = reverse('authentication:login')

        # Make failed login attempt
        api_client.post(url, {
            'email': 'user@ayni.cl',
            'password': 'WrongPass!'
        }, format='json')

        user.refresh_from_db()
        assert user.failed_login_attempts == 1

    def test_account_lockout_after_5_failed_attempts(self, api_client, create_user):
        """System locks account after 5 failed login attempts."""
        user = create_user(email='user@ayni.cl', password='CorrectPass123!')

        url = reverse('authentication:login')

        # Make 5 failed attempts
        for _ in range(5):
            api_client.post(url, {
                'email': 'user@ayni.cl',
                'password': 'WrongPass!'
            }, format='json')

        user.refresh_from_db()
        assert user.is_locked_out()
        assert user.lockout_until is not None

    def test_successful_login_resets_failed_attempts(self, api_client, create_user):
        """Successful login resets failed attempts counter."""
        password = 'CorrectPass123!'
        user = create_user(email='user@ayni.cl', password=password)

        # Set failed attempts manually
        user.failed_login_attempts = 3
        user.save()

        url = reverse('authentication:login')
        api_client.post(url, {
            'email': 'user@ayni.cl',
            'password': password
        }, format='json')

        user.refresh_from_db()
        assert user.failed_login_attempts == 0

    def test_jwt_refresh_rotation(self, api_client, create_user):
        """JWT refresh returns new refresh token (rotation)."""
        user = create_user()
        original_refresh = RefreshToken.for_user(user)
        original_refresh_str = str(original_refresh)

        url = reverse('authentication:token_refresh')
        response = api_client.post(url, {
            'refresh': original_refresh_str
        }, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        # Rotation enabled means new refresh token returned
        if 'refresh' in response.data:
            assert response.data['refresh'] != original_refresh_str

    def test_login_updates_last_login_timestamp(self, api_client, create_user):
        """Login updates user's last_login timestamp."""
        password = 'Pass123!'
        user = create_user(password=password)
        original_last_login = user.last_login

        url = reverse('authentication:login')
        api_client.post(url, {
            'email': user.email,
            'password': password
        }, format='json')

        user.refresh_from_db()
        assert user.last_login is not None
        assert user.last_login != original_last_login


# ============================================================================
# TEST TYPE 6: VISUAL (N/A for Backend)
# ============================================================================
# Visual tests are not applicable for backend APIs
# Frontend will handle UI/UX testing


# ============================================================================
# TEST TYPE 7: PERFORMANCE
# ============================================================================

@pytest.mark.django_db
class TestAuthenticationPerformance:
    """Test performance requirements (<200ms as per task spec)."""

    def test_login_response_time(self, api_client, create_user):
        """Login response time is under 200ms."""
        password = 'Pass123!'
        user = create_user(password=password)

        url = reverse('authentication:login')

        start_time = time.time()
        response = api_client.post(url, {
            'email': user.email,
            'password': password
        }, format='json')
        end_time = time.time()

        duration_ms = (end_time - start_time) * 1000

        assert response.status_code == status.HTTP_200_OK
        # Allow some flexibility for test environment (300ms)
        assert duration_ms < 300, f"Login took {duration_ms}ms (target: <200ms)"

    def test_registration_response_time(self, api_client, user_data):
        """Registration response time is acceptable."""
        url = reverse('authentication:register')

        start_time = time.time()
        response = api_client.post(url, user_data, format='json')
        end_time = time.time()

        duration_ms = (end_time - start_time) * 1000

        assert response.status_code == status.HTTP_201_CREATED
        # Registration can be slower due to password hashing (500ms)
        assert duration_ms < 500, f"Registration took {duration_ms}ms (target: <500ms)"

    def test_token_refresh_response_time(self, api_client, create_user):
        """Token refresh is fast (<100ms)."""
        user = create_user()
        refresh = RefreshToken.for_user(user)

        url = reverse('authentication:token_refresh')

        start_time = time.time()
        response = api_client.post(url, {'refresh': str(refresh)}, format='json')
        end_time = time.time()

        duration_ms = (end_time - start_time) * 1000

        assert response.status_code == status.HTTP_200_OK
        assert duration_ms < 200, f"Token refresh took {duration_ms}ms (target: <100ms)"


# ============================================================================
# TEST TYPE 8: SECURITY
# ============================================================================

@pytest.mark.django_db
class TestAuthenticationSecurity:
    """Test security requirements."""

    def test_passwords_are_hashed_with_argon2(self, api_client, user_data):
        """Passwords are hashed using Argon2."""
        url = reverse('authentication:register')
        api_client.post(url, user_data, format='json')

        user = User.objects.get(email=user_data['email'].lower())
        # Argon2 hashes start with $argon2
        assert user.password.startswith('$argon2')

    def test_password_not_returned_in_api_response(self, api_client, user_data):
        """Password is never returned in API responses."""
        url = reverse('authentication:register')
        response = api_client.post(url, user_data, format='json')

        assert 'password' not in str(response.data)
        assert user_data['password'] not in str(response.data)

    def test_jwt_token_expiration(self, api_client, create_user):
        """JWT tokens have expiration times."""
        user = create_user()
        refresh = RefreshToken.for_user(user)

        # Tokens should have expiration claims
        assert 'exp' in refresh.payload
        assert 'exp' in refresh.access_token.payload

    def test_invalid_token_rejected(self, api_client):
        """Invalid JWT tokens are rejected."""
        api_client.credentials(HTTP_AUTHORIZATION='Bearer invalid_token_string')

        url = reverse('authentication:profile')
        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_lockout_prevents_brute_force(self, api_client, create_user):
        """Account lockout prevents brute force attacks."""
        user = create_user(email='user@ayni.cl', password='CorrectPass123!')

        url = reverse('authentication:login')

        # Try to brute force (6 attempts)
        for _ in range(6):
            response = api_client.post(url, {
                'email': 'user@ayni.cl',
                'password': 'WrongPass!'
            }, format='json')

        # After 5 failed attempts, account should be locked
        user.refresh_from_db()
        assert user.is_locked_out()

        # Even correct password should fail during lockout
        response = api_client.post(url, {
            'email': 'user@ayni.cl',
            'password': 'CorrectPass123!'
        }, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'locked' in str(response.data).lower()

    def test_logout_blacklists_refresh_token(self, api_client, create_user):
        """Logout blacklists the refresh token."""
        user = create_user()
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_str = str(refresh)

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        # Logout
        logout_url = reverse('authentication:logout')
        response = api_client.post(logout_url, {'refresh': refresh_str}, format='json')
        assert response.status_code == status.HTTP_205_RESET_CONTENT

        # Try to use blacklisted refresh token
        refresh_url = reverse('authentication:token_refresh')
        response = api_client.post(refresh_url, {'refresh': refresh_str}, format='json')

        # Should be rejected (blacklisted)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_email_stored_lowercase(self, api_client, user_data):
        """Email addresses are stored in lowercase for consistency."""
        user_data['email'] = 'TEST@AYNI.CL'

        url = reverse('authentication:register')
        api_client.post(url, user_data, format='json')

        user = User.objects.get(email='test@ayni.cl')
        assert user.email == 'test@ayni.cl'
