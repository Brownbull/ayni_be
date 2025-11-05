"""
Django admin configuration for authentication models.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, PasswordResetToken, EmailVerificationToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin interface for User model."""

    list_display = [
        'email', 'username', 'is_email_verified',
        'is_active', 'is_staff', 'created_at'
    ]
    list_filter = ['is_staff', 'is_active', 'is_email_verified', 'created_at']
    search_fields = ['email', 'username']
    ordering = ['-created_at']

    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser',
                      'groups', 'user_permissions'),
        }),
        ('Security', {
            'fields': ('is_email_verified', 'last_login_ip',
                      'failed_login_attempts', 'lockout_until'),
        }),
        ('Important dates', {'fields': ('last_login', 'created_at')}),
    )

    readonly_fields = ['created_at', 'last_login']


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Admin interface for PasswordResetToken model."""

    list_display = ['user', 'created_at', 'expires_at', 'used']
    list_filter = ['used', 'created_at', 'expires_at']
    search_fields = ['user__email', 'token']
    readonly_fields = ['created_at']
    ordering = ['-created_at']


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    """Admin interface for EmailVerificationToken model."""

    list_display = ['user', 'created_at', 'expires_at', 'verified']
    list_filter = ['verified', 'created_at', 'expires_at']
    search_fields = ['user__email', 'token']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
