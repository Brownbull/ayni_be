"""
Django admin configuration for company models.
"""

from django.contrib import admin
from .models import Company, UserCompany


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Admin interface for Company model."""

    list_display = ['name', 'rut', 'industry', 'size', 'is_active', 'created_at']
    list_filter = ['industry', 'size', 'is_active', 'created_at']
    search_fields = ['name', 'rut']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    fieldsets = (
        ('Company Information', {
            'fields': ('name', 'rut', 'industry', 'size')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserCompany)
class UserCompanyAdmin(admin.ModelAdmin):
    """Admin interface for UserCompany relationship model."""

    list_display = ['user', 'company', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'created_at']
    search_fields = ['user__email', 'company__name', 'company__rut']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

    fieldsets = (
        ('Relationship', {
            'fields': ('user', 'company', 'role')
        }),
        ('Permissions', {
            'fields': ('permissions', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
