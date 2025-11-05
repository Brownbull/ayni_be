"""
Company management models for AYNI platform.

This module defines companies, user-company relationships, and permissions.
Implements multi-tenant data isolation for Chilean PYMEs.
"""

from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone
from django.conf import settings


# Chilean RUT validator
rut_validator = RegexValidator(
    regex=r'^\d{1,2}\.\d{3}\.\d{3}-[\dkK]$',
    message='RUT must be in format: XX.XXX.XXX-X'
)


class Company(models.Model):
    """
    Company model representing Chilean PYMEs.

    Attributes:
        name: Company legal name
        rut: Chilean RUT (tax identifier)
        industry: Industry code/category
        size: Company size category
        created_at: Registration timestamp
        updated_at: Last modification timestamp
        is_active: Soft delete flag
    """

    INDUSTRY_CHOICES = [
        ('retail', 'Retail / Comercio'),
        ('food', 'Food & Beverage / Alimentos y Bebidas'),
        ('manufacturing', 'Manufacturing / Manufactura'),
        ('services', 'Services / Servicios'),
        ('technology', 'Technology / Tecnología'),
        ('construction', 'Construction / Construcción'),
        ('agriculture', 'Agriculture / Agricultura'),
        ('healthcare', 'Healthcare / Salud'),
        ('education', 'Education / Educación'),
        ('other', 'Other / Otro'),
    ]

    SIZE_CHOICES = [
        ('micro', 'Micro (1-9 employees)'),
        ('small', 'Small (10-49 employees)'),
        ('medium', 'Medium (50-249 employees)'),
    ]

    name = models.CharField(max_length=255)
    rut = models.CharField(
        max_length=15,
        unique=True,
        validators=[rut_validator],
        help_text='Chilean RUT in format XX.XXX.XXX-X'
    )
    industry = models.CharField(
        max_length=50,
        choices=INDUSTRY_CHOICES,
        default='other'
    )
    size = models.CharField(
        max_length=20,
        choices=SIZE_CHOICES,
        default='micro'
    )

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Soft delete
    is_active = models.BooleanField(default=True, db_index=True)

    # Many-to-many relationship with users
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='UserCompany',
        related_name='companies'
    )

    class Meta:
        db_table = 'companies'
        verbose_name_plural = 'companies'
        indexes = [
            models.Index(fields=['rut']),
            models.Index(fields=['industry']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.rut})"

    def soft_delete(self):
        """Soft delete company instead of hard delete."""
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])


class UserCompany(models.Model):
    """
    User-Company relationship with roles and permissions.

    Attributes:
        user: Associated user
        company: Associated company
        role: User's role in the company
        permissions: JSON field for fine-grained permissions
        created_at: Relationship creation timestamp
        is_active: Whether relationship is active
    """

    ROLE_CHOICES = [
        ('owner', 'Owner / Dueño'),
        ('admin', 'Administrator / Administrador'),
        ('manager', 'Manager / Gerente'),
        ('analyst', 'Analyst / Analista'),
        ('viewer', 'Viewer / Visualizador'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_companies'
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='company_users'
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='viewer'
    )

    # Granular permissions stored as JSON
    permissions = models.JSONField(
        default=dict,
        help_text='Fine-grained permissions: {can_upload: true, can_export: false, ...}'
    )

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = 'user_companies'
        unique_together = ['user', 'company']
        indexes = [
            models.Index(fields=['user', 'company']),
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.company.name} ({self.role})"

    def has_permission(self, permission_name):
        """Check if user has a specific permission for this company."""
        # Owner and admin have all permissions
        if self.role in ['owner', 'admin']:
            return True

        # Check custom permissions
        return self.permissions.get(permission_name, False)

    @staticmethod
    def get_default_permissions(role):
        """Get default permissions for a given role."""
        permissions_map = {
            'owner': {
                'can_view': True,
                'can_upload': True,
                'can_export': True,
                'can_manage_users': True,
                'can_delete_data': True,
                'can_manage_company': True,
            },
            'admin': {
                'can_view': True,
                'can_upload': True,
                'can_export': True,
                'can_manage_users': True,
                'can_delete_data': False,
                'can_manage_company': False,
            },
            'manager': {
                'can_view': True,
                'can_upload': True,
                'can_export': True,
                'can_manage_users': False,
                'can_delete_data': False,
                'can_manage_company': False,
            },
            'analyst': {
                'can_view': True,
                'can_upload': False,
                'can_export': True,
                'can_manage_users': False,
                'can_delete_data': False,
                'can_manage_company': False,
            },
            'viewer': {
                'can_view': True,
                'can_upload': False,
                'can_export': False,
                'can_manage_users': False,
                'can_delete_data': False,
                'can_manage_company': False,
            },
        }
        return permissions_map.get(role, permissions_map['viewer'])
