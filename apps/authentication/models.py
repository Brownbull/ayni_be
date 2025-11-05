"""
Authentication models for AYNI platform.

This module defines the User model and related authentication entities.
Following Django best practices with AbstractUser for extensibility.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import EmailValidator
from django.utils import timezone


class User(AbstractUser):
    """
    Custom user model extending Django's AbstractUser.

    Attributes:
        email: Unique email address (primary identifier)
        created_at: Timestamp of account creation
        updated_at: Timestamp of last update
        is_email_verified: Email verification status
        last_login_ip: Last known login IP for security
        failed_login_attempts: Counter for failed logins (rate limiting)
        lockout_until: Temporary lockout timestamp for security
    """

    # Override email to make it unique and required
    email = models.EmailField(
        unique=True,
        validators=[EmailValidator()],
        error_messages={
            'unique': "A user with that email already exists.",
        }
    )

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Security fields
    is_email_verified = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    lockout_until = models.DateTimeField(null=True, blank=True)

    # Use email as the primary authentication field
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']  # Username is required by AbstractUser

    # Override groups and user_permissions to avoid clashes
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='ayni_user_set',
        related_query_name='ayni_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='ayni_user_set',
        related_query_name='ayni_user',
    )

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} ({self.username})"

    def is_locked_out(self):
        """Check if user is currently locked out due to failed login attempts."""
        if self.lockout_until and self.lockout_until > timezone.now():
            return True
        return False

    def reset_failed_attempts(self):
        """Reset failed login attempts counter."""
        self.failed_login_attempts = 0
        self.lockout_until = None
        self.save(update_fields=['failed_login_attempts', 'lockout_until'])

    def increment_failed_attempts(self):
        """Increment failed login attempts and apply lockout if threshold reached."""
        self.failed_login_attempts += 1

        # Lockout for 15 minutes after 5 failed attempts
        if self.failed_login_attempts >= 5:
            self.lockout_until = timezone.now() + timezone.timedelta(minutes=15)

        self.save(update_fields=['failed_login_attempts', 'lockout_until'])


class PasswordResetToken(models.Model):
    """
    Password reset tokens for secure password recovery.

    Attributes:
        user: Associated user
        token: Unique token string
        created_at: Token creation timestamp
        expires_at: Token expiration timestamp
        used: Whether token has been used
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_reset_tokens'
    )
    token = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        db_table = 'password_reset_tokens'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['expires_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Reset token for {self.user.email}"

    def is_valid(self):
        """Check if token is still valid (not expired and not used)."""
        return not self.used and self.expires_at > timezone.now()


class EmailVerificationToken(models.Model):
    """
    Email verification tokens for confirming user email addresses.

    Attributes:
        user: Associated user
        token: Unique token string
        created_at: Token creation timestamp
        expires_at: Token expiration timestamp
        verified: Whether email has been verified
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='email_verification_tokens'
    )
    token = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    verified = models.BooleanField(default=False)

    class Meta:
        db_table = 'email_verification_tokens'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['expires_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Verification token for {self.user.email}"

    def is_valid(self):
        """Check if token is still valid (not verified and not expired)."""
        return not self.verified and self.expires_at > timezone.now()
