"""
Authentication serializers for AYNI platform.

This module defines serializers for user registration, login, and profile management.
Uses Django REST Framework for API serialization.
"""

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from .models import User


class UserRegisterSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration.

    Validates email, username, and password requirements.
    Creates user with hashed password (Argon2).
    """

    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        help_text="Password must be at least 8 characters"
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        help_text="Confirm your password"
    )
    email = serializers.EmailField(
        required=True,
        help_text="Valid email address (will be verified)"
    )
    username = serializers.CharField(
        required=True,
        max_length=150,
        help_text="Unique username (alphanumeric and @/./+/-/_ only)"
    )

    class Meta:
        model = User
        fields = ('email', 'username', 'password', 'password_confirm', 'first_name', 'last_name')
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
        }

    def validate_email(self, value):
        """Validate email is unique and properly formatted."""
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError(
                "A user with that email already exists. Please login instead."
            )
        return value.lower()

    def validate_username(self, value):
        """Validate username is unique."""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(
                "A user with that username already exists. Please choose another."
            )
        return value

    def validate(self, attrs):
        """Validate password requirements and confirmation match."""
        password = attrs.get('password')
        password_confirm = attrs.pop('password_confirm', None)

        # Check passwords match
        if password != password_confirm:
            raise serializers.ValidationError({
                "password_confirm": "Passwords do not match."
            })

        # Validate password strength using Django's validators
        try:
            validate_password(password)
        except DjangoValidationError as e:
            raise serializers.ValidationError({
                "password": list(e.messages)
            })

        return attrs

    def create(self, validated_data):
        """Create user with hashed password."""
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data['username'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login.

    Authenticates user with email and password.
    Returns user data and JWT tokens on success.
    """

    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )

    def validate(self, attrs):
        """Authenticate user and check lockout status."""
        email = attrs.get('email', '').lower()
        password = attrs.get('password')

        if not email or not password:
            raise serializers.ValidationError(
                "Both email and password are required."
            )

        # Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid credentials. Please try again."
            )

        # Check if user is locked out
        if user.is_locked_out():
            lockout_remaining = (user.lockout_until - timezone.now()).total_seconds() / 60
            raise serializers.ValidationError(
                f"Account is temporarily locked due to failed login attempts. "
                f"Please try again in {int(lockout_remaining)} minutes."
            )

        # Authenticate user
        user = authenticate(username=email, password=password)

        if user is None:
            # Increment failed attempts for the user
            try:
                failed_user = User.objects.get(email=email)
                failed_user.increment_failed_attempts()

                if failed_user.failed_login_attempts >= 5:
                    raise serializers.ValidationError(
                        "Too many failed login attempts. Account locked for 15 minutes."
                    )
                else:
                    attempts_remaining = 5 - failed_user.failed_login_attempts
                    raise serializers.ValidationError(
                        f"Invalid credentials. {attempts_remaining} attempts remaining."
                    )
            except User.DoesNotExist:
                raise serializers.ValidationError(
                    "Invalid credentials. Please try again."
                )

        # Check if user is active
        if not user.is_active:
            raise serializers.ValidationError(
                "This account has been disabled. Please contact support."
            )

        # Reset failed attempts on successful login
        user.reset_failed_attempts()

        attrs['user'] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile data.

    Returns safe user information (no sensitive fields).
    """

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'is_email_verified',
            'created_at',
            'last_login',
        )
        read_only_fields = ('id', 'email', 'created_at', 'last_login')


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user profile.

    Allows updating first_name, last_name only.
    Email and username changes require separate verification flow.
    """

    class Meta:
        model = User
        fields = ('first_name', 'last_name')

    def validate(self, attrs):
        """Validate profile update data."""
        # Additional validation logic can be added here
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing user password.

    Requires current password for verification.
    """

    current_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )
    new_password_confirm = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )

    def validate_current_password(self, value):
        """Validate current password is correct."""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(
                "Current password is incorrect."
            )
        return value

    def validate(self, attrs):
        """Validate new password requirements and confirmation."""
        new_password = attrs.get('new_password')
        new_password_confirm = attrs.get('new_password_confirm')

        # Check passwords match
        if new_password != new_password_confirm:
            raise serializers.ValidationError({
                "new_password_confirm": "New passwords do not match."
            })

        # Validate password strength
        try:
            validate_password(new_password, self.context['request'].user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({
                "new_password": list(e.messages)
            })

        return attrs

    def save(self):
        """Update user password."""
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        return user
