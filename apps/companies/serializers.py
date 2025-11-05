"""
Company management serializers for AYNI platform.

This module provides DRF serializers for companies and user-company relationships.
Implements validation for Chilean RUT, industry codes, and permission management.
"""

from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import Company, UserCompany


def validate_chilean_rut(rut):
    """
    Validate Chilean RUT format and check digit.

    Args:
        rut: String in format XX.XXX.XXX-X

    Returns:
        Cleaned RUT string

    Raises:
        ValidationError: If RUT format or check digit is invalid
    """
    import re

    # Remove dots and dash for validation
    clean_rut = rut.replace('.', '').replace('-', '')

    if not clean_rut:
        raise serializers.ValidationError("RUT cannot be empty")

    # Separate number and check digit
    number = clean_rut[:-1]
    check_digit = clean_rut[-1].upper()

    if not number.isdigit():
        raise serializers.ValidationError("RUT number must contain only digits")

    # Calculate check digit
    reversed_digits = map(int, reversed(number))
    factors = [2, 3, 4, 5, 6, 7]
    s = sum(d * factors[i % 6] for i, d in enumerate(reversed_digits))
    remainder = s % 11
    calculated_check = 11 - remainder

    if calculated_check == 11:
        expected_check = '0'
    elif calculated_check == 10:
        expected_check = 'K'
    else:
        expected_check = str(calculated_check)

    if check_digit != expected_check:
        raise serializers.ValidationError(
            f"Invalid RUT check digit. Expected {expected_check}, got {check_digit}"
        )

    return rut


class CompanySerializer(serializers.ModelSerializer):
    """
    Serializer for Company model with validation and user context.

    Includes:
    - Chilean RUT validation
    - Industry code validation
    - User role/permission context
    - Soft delete support
    """

    # Read-only fields
    id = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    # User context (added dynamically in views)
    user_role = serializers.SerializerMethodField()
    user_permissions = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id',
            'name',
            'rut',
            'industry',
            'size',
            'created_at',
            'updated_at',
            'is_active',
            'user_role',
            'user_permissions',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_rut(self, value):
        """Validate Chilean RUT format and check digit."""
        # Validate format and check digit
        validated_rut = validate_chilean_rut(value)

        # Check for duplicates (excluding current instance on update)
        queryset = Company.objects.filter(rut=validated_rut)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError("A company with this RUT already exists")

        return validated_rut

    def validate_name(self, value):
        """Validate company name."""
        if not value or not value.strip():
            raise serializers.ValidationError("Company name cannot be empty")

        if len(value.strip()) < 2:
            raise serializers.ValidationError("Company name must be at least 2 characters long")

        return value.strip()

    def validate_industry(self, value):
        """Validate industry code."""
        valid_industries = [choice[0] for choice in Company.INDUSTRY_CHOICES]
        if value not in valid_industries:
            raise serializers.ValidationError(
                f"Invalid industry code. Must be one of: {', '.join(valid_industries)}"
            )
        return value

    def validate_size(self, value):
        """Validate company size."""
        valid_sizes = [choice[0] for choice in Company.SIZE_CHOICES]
        if value not in valid_sizes:
            raise serializers.ValidationError(
                f"Invalid size. Must be one of: {', '.join(valid_sizes)}"
            )
        return value

    def get_user_role(self, obj):
        """Get current user's role for this company."""
        user = self.context.get('request')and self.context['request'].user
        if not user or not user.is_authenticated:
            return None

        try:
            user_company = UserCompany.objects.get(user=user, company=obj, is_active=True)
            return user_company.role
        except UserCompany.DoesNotExist:
            return None

    def get_user_permissions(self, obj):
        """Get current user's permissions for this company."""
        user = self.context.get('request') and self.context['request'].user
        if not user or not user.is_authenticated:
            return None

        try:
            user_company = UserCompany.objects.get(user=user, company=obj, is_active=True)
            return user_company.permissions
        except UserCompany.DoesNotExist:
            return None


class CompanyCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for company creation.

    Automatically creates UserCompany relationship with 'owner' role.
    """

    class Meta:
        model = Company
        fields = ['name', 'rut', 'industry', 'size']

    def validate_rut(self, value):
        """Validate Chilean RUT format and check digit."""
        return validate_chilean_rut(value)

    def validate_name(self, value):
        """Validate company name."""
        if not value or not value.strip():
            raise serializers.ValidationError("Company name cannot be empty")

        if len(value.strip()) < 2:
            raise serializers.ValidationError("Company name must be at least 2 characters long")

        return value.strip()

    def create(self, validated_data):
        """
        Create company and associate with current user as owner.

        Args:
            validated_data: Validated company data

        Returns:
            Created Company instance with UserCompany relationship
        """
        # Get current user from context
        user = self.context['request'].user

        # Create company
        company = Company.objects.create(**validated_data)

        # Create UserCompany relationship with owner role
        UserCompany.objects.create(
            user=user,
            company=company,
            role='owner',
            permissions=UserCompany.get_default_permissions('owner')
        )

        return company


class UserCompanySerializer(serializers.ModelSerializer):
    """
    Serializer for UserCompany relationships.

    Manages user roles and permissions for companies.
    """

    # Nested user information
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)

    # Nested company information
    company_name = serializers.CharField(source='company.name', read_only=True)
    company_rut = serializers.CharField(source='company.rut', read_only=True)

    class Meta:
        model = UserCompany
        fields = [
            'id',
            'user',
            'user_email',
            'user_username',
            'company',
            'company_name',
            'company_rut',
            'role',
            'permissions',
            'created_at',
            'is_active',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_role(self, value):
        """Validate role choice."""
        valid_roles = [choice[0] for choice in UserCompany.ROLE_CHOICES]
        if value not in valid_roles:
            raise serializers.ValidationError(
                f"Invalid role. Must be one of: {', '.join(valid_roles)}"
            )
        return value

    def validate(self, attrs):
        """
        Validate UserCompany relationship.

        Ensures:
        - User has permission to manage company users
        - At least one owner exists per company
        """
        user = self.context['request'].user
        company = attrs.get('company') or (self.instance and self.instance.company)

        # Check if user has permission to manage company users
        try:
            user_company = UserCompany.objects.get(
                user=user,
                company=company,
                is_active=True
            )
            if not user_company.has_permission('can_manage_users'):
                raise serializers.ValidationError(
                    "You don't have permission to manage users for this company"
                )
        except UserCompany.DoesNotExist:
            raise serializers.ValidationError(
                "You don't have access to this company"
            )

        return attrs

    def create(self, validated_data):
        """Create UserCompany with default permissions."""
        role = validated_data.get('role', 'viewer')

        # Set default permissions if not provided
        if 'permissions' not in validated_data or not validated_data['permissions']:
            validated_data['permissions'] = UserCompany.get_default_permissions(role)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update UserCompany and refresh permissions if role changes."""
        new_role = validated_data.get('role')

        # If role changes, update permissions
        if new_role and new_role != instance.role:
            validated_data['permissions'] = UserCompany.get_default_permissions(new_role)

        return super().update(instance, validated_data)
