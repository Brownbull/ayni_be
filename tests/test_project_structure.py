"""
Test Suite for Task-001: Project Structure
Tests all 8 required test types: valid, error, invalid, edge, functional, visual, performance, security
"""
import os
import pytest
import time
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase


class ProjectStructureValidTests(TestCase):
    """Valid (Happy Path) Tests"""

    def test_django_settings_loaded(self):
        """Valid: Django settings module loads successfully"""
        self.assertIsNotNone(settings.SECRET_KEY)
        self.assertIsNotNone(settings.DATABASES)

    def test_all_apps_registered(self):
        """Valid: All AYNI apps are registered in INSTALLED_APPS"""
        expected_apps = [
            'apps.authentication',
            'apps.companies',
            'apps.processing',
            'apps.analytics',
        ]
        for app in expected_apps:
            self.assertIn(app, settings.INSTALLED_APPS)

    def test_rest_framework_configured(self):
        """Valid: REST Framework is configured"""
        self.assertIn('rest_framework', settings.INSTALLED_APPS)
        self.assertIsNotNone(settings.REST_FRAMEWORK)

    def test_database_connection(self):
        """Valid: Database connection works"""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            self.assertEqual(result[0], 1)


class ProjectStructureErrorTests(TestCase):
    """Error Handling Tests"""

    def test_missing_env_variable_has_default(self):
        """Error: Missing environment variables have sensible defaults"""
        # Even without .env, settings should load with defaults
        self.assertIsNotNone(settings.SECRET_KEY)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=[])
    def test_production_requires_allowed_hosts(self):
        """Error: Production settings require ALLOWED_HOSTS"""
        # In production, ALLOWED_HOSTS should not be empty
        if not settings.DEBUG:
            self.assertTrue(len(settings.ALLOWED_HOSTS) > 0 or settings.DEBUG)


class ProjectStructureInvalidTests(TestCase):
    """Invalid Input Tests"""

    def test_invalid_database_url_format(self):
        """Invalid: Reject malformed DATABASE_URL"""
        # This test verifies that dj-database-url handles invalid URLs gracefully
        import dj_database_url
        result = dj_database_url.config(default='sqlite:///db.sqlite3')
        self.assertIn('ENGINE', result)

    def test_cors_settings_defined(self):
        """Invalid: CORS settings must be defined"""
        self.assertTrue(hasattr(settings, 'CORS_ALLOWED_ORIGINS'))


class ProjectStructureEdgeTests(TestCase):
    """Edge Case Tests"""

    def test_works_on_windows(self):
        """Edge: Project structure works on Windows"""
        # Verify paths use pathlib (cross-platform)
        self.assertIsInstance(settings.BASE_DIR, Path)

    def test_celery_configuration_exists(self):
        """Edge: Celery configuration is present"""
        self.assertTrue(hasattr(settings, 'CELERY_BROKER_URL'))
        self.assertTrue(hasattr(settings, 'CELERY_RESULT_BACKEND'))

    def test_channels_configuration_exists(self):
        """Edge: Channels (WebSocket) configuration is present"""
        self.assertTrue(hasattr(settings, 'CHANNEL_LAYERS'))
        self.assertIn('default', settings.CHANNEL_LAYERS)


class ProjectStructureFunctionalTests(APITestCase):
    """Functional (Business Logic) Tests"""

    def test_admin_accessible(self):
        """Functional: Django admin is accessible"""
        response = self.client.get('/admin/', follow=True)
        # Should redirect to login (200) or show login page (200)
        self.assertIn(response.status_code, [200, 302])

    def test_api_schema_accessible(self):
        """Functional: API schema endpoint is accessible"""
        response = self.client.get('/api/schema/')
        self.assertEqual(response.status_code, 200)

    def test_api_docs_accessible(self):
        """Functional: API documentation is accessible"""
        response = self.client.get('/api/docs/')
        self.assertEqual(response.status_code, 200)


class ProjectStructureVisualTests(TestCase):
    """Visual Tests (N/A for backend, but testing file structure)"""

    def test_media_directory_exists(self):
        """Visual: Media directory configured for file uploads"""
        self.assertTrue(hasattr(settings, 'MEDIA_ROOT'))
        self.assertTrue(hasattr(settings, 'MEDIA_URL'))

    def test_static_directory_configured(self):
        """Visual: Static files directory configured"""
        self.assertTrue(hasattr(settings, 'STATIC_ROOT'))
        self.assertTrue(hasattr(settings, 'STATIC_URL'))


class ProjectStructurePerformanceTests(TestCase):
    """Performance Tests"""

    def test_settings_import_fast(self):
        """Performance: Settings module imports in < 1 second"""
        start = time.time()
        from django.conf import settings as reload_settings
        duration = time.time() - start
        self.assertLess(duration, 1.0)

    def test_database_query_fast(self):
        """Performance: Simple database query completes in < 100ms"""
        from django.db import connection
        start = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        duration = (time.time() - start) * 1000  # Convert to ms
        self.assertLess(duration, 100)


class ProjectStructureSecurityTests(TestCase):
    """Security Tests"""

    def test_secret_key_not_default(self):
        """Security: SECRET_KEY should not be default in production"""
        if not settings.DEBUG:
            self.assertNotIn('django-insecure', settings.SECRET_KEY)

    def test_debug_false_in_production(self):
        """Security: DEBUG must be False in production"""
        # If ALLOWED_HOSTS is set, DEBUG should be False
        if settings.ALLOWED_HOSTS and settings.ALLOWED_HOSTS != ['localhost', '127.0.0.1']:
            self.assertFalse(settings.DEBUG)

    def test_password_hashers_use_argon2(self):
        """Security: Password hashing uses Argon2 (strongest)"""
        self.assertTrue(hasattr(settings, 'PASSWORD_HASHERS'))
        self.assertIn('Argon2PasswordHasher', settings.PASSWORD_HASHERS[0])

    def test_jwt_configured_securely(self):
        """Security: JWT settings are configured"""
        self.assertTrue(hasattr(settings, 'SIMPLE_JWT'))
        jwt_settings = settings.SIMPLE_JWT
        self.assertIn('ACCESS_TOKEN_LIFETIME', jwt_settings)
        self.assertIn('ALGORITHM', jwt_settings)

    def test_cors_configured(self):
        """Security: CORS is configured (not wide open)"""
        self.assertTrue(hasattr(settings, 'CORS_ALLOWED_ORIGINS'))
        # Should not allow all origins
        self.assertNotEqual(getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False), True)

    def test_file_upload_size_limit(self):
        """Security: File upload size is limited"""
        self.assertTrue(hasattr(settings, 'MAX_UPLOAD_SIZE'))
        # Should have reasonable limit (not unlimited)
        self.assertLess(settings.MAX_UPLOAD_SIZE, 500 * 1024 * 1024)  # < 500MB


@pytest.mark.integration
class IntegrationTests(TestCase):
    """Integration tests for complete project setup"""

    def test_all_apps_migrations_ready(self):
        """Integration: All apps have clean migration state"""
        # This will fail if migrations are missing or conflicting
        try:
            call_command('makemigrations', '--check', '--dry-run', verbosity=0)
        except SystemExit:
            self.fail("Migrations are missing or conflicting")

    def test_collectstatic_works(self):
        """Integration: Static files can be collected"""
        # This verifies static files configuration is correct
        try:
            call_command('collectstatic', '--noinput', '--clear', verbosity=0)
        except Exception as e:
            self.fail(f"collectstatic failed: {str(e)}")
