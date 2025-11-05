"""
Authentication views for AYNI platform.

This module provides JWT-based authentication endpoints:
- Register: Create new user account
- Login: Authenticate and receive JWT tokens
- Logout: Invalidate refresh token (if using blacklist)
- Refresh: Get new access token
- Profile: View and update user profile
- Change Password: Update user password
"""

from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.utils import timezone

from .models import User
from .serializers import (
    UserRegisterSerializer,
    UserLoginSerializer,
    UserSerializer,
    UserProfileUpdateSerializer,
    ChangePasswordSerializer,
)


class RegisterView(APIView):
    """
    User registration endpoint.

    POST: Create a new user account with email and password.
    Returns user data and JWT tokens on success.
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegisterSerializer

    @extend_schema(
        request=UserRegisterSerializer,
        responses={
            201: OpenApiResponse(
                response=UserSerializer,
                description="User created successfully. JWT tokens returned."
            ),
            400: OpenApiResponse(description="Validation error (email exists, weak password, etc)"),
        },
        description="Register a new user account. Returns JWT access and refresh tokens.",
    )
    def post(self, request):
        """Create new user account."""
        serializer = UserRegisterSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)

            # Track login IP
            user.last_login_ip = self.get_client_ip(request)
            user.save(update_fields=['last_login_ip'])

            return Response({
                'user': UserSerializer(user).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                'message': 'Registration successful. Welcome to AYNI!'
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_client_ip(self, request):
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class LoginView(APIView):
    """
    User login endpoint.

    POST: Authenticate user with email and password.
    Returns user data and JWT tokens on success.
    Implements rate limiting via failed login attempts.
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = UserLoginSerializer

    @extend_schema(
        request=UserLoginSerializer,
        responses={
            200: OpenApiResponse(
                response=UserSerializer,
                description="Login successful. JWT tokens returned."
            ),
            400: OpenApiResponse(description="Invalid credentials or account locked"),
            401: OpenApiResponse(description="Authentication failed"),
        },
        description="Login with email and password. Returns JWT access and refresh tokens.",
    )
    def post(self, request):
        """Authenticate user and return JWT tokens."""
        serializer = UserLoginSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)

            # Update last login timestamp and IP
            user.last_login = timezone.now()
            user.last_login_ip = self.get_client_ip(request)
            user.save(update_fields=['last_login', 'last_login_ip'])

            return Response({
                'user': UserSerializer(user).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                'message': 'Login successful. Welcome back!'
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_client_ip(self, request):
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class LogoutView(APIView):
    """
    User logout endpoint.

    POST: Blacklist the refresh token to invalidate it.
    Requires authentication.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request={'application/json': {'type': 'object', 'properties': {'refresh': {'type': 'string'}}}},
        responses={
            205: OpenApiResponse(description="Logout successful"),
            400: OpenApiResponse(description="Invalid or missing refresh token"),
        },
        description="Logout by blacklisting the refresh token. Access token remains valid until expiry.",
    )
    def post(self, request):
        """Blacklist refresh token."""
        try:
            refresh_token = request.data.get('refresh')

            if not refresh_token:
                return Response(
                    {'error': 'Refresh token is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(
                {'message': 'Logout successful'},
                status=status.HTTP_205_RESET_CONTENT
            )

        except TokenError as e:
            return Response(
                {'error': 'Invalid or expired token'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': 'An error occurred during logout'},
                status=status.HTTP_400_BAD_REQUEST
            )


class ProfileView(generics.RetrieveUpdateAPIView):
    """
    User profile endpoint.

    GET: Retrieve current user's profile
    PATCH/PUT: Update profile (first_name, last_name)
    Requires authentication.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        """Return the current authenticated user."""
        return self.request.user

    @extend_schema(
        responses={
            200: UserSerializer,
        },
        description="Get current user's profile information.",
    )
    def get(self, request, *args, **kwargs):
        """Get current user profile."""
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=UserProfileUpdateSerializer,
        responses={
            200: UserSerializer,
        },
        description="Update current user's profile (first_name, last_name).",
    )
    def patch(self, request, *args, **kwargs):
        """Update current user profile."""
        serializer = UserProfileUpdateSerializer(
            self.get_object(),
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                UserSerializer(self.get_object()).data,
                status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """
    Change password endpoint.

    POST: Change user's password (requires current password)
    Requires authentication.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password changed successfully"),
            400: OpenApiResponse(description="Validation error (current password incorrect, weak new password, etc)"),
        },
        description="Change user password. Requires current password for verification.",
    )
    def post(self, request):
        """Change user password."""
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Password changed successfully'
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TokenRefreshView(TokenRefreshView):
    """
    JWT token refresh endpoint.

    POST: Get new access token using refresh token.
    Extends djangorestframework-simplejwt's TokenRefreshView.
    """

    @extend_schema(
        responses={
            200: OpenApiResponse(description="New access token issued"),
            401: OpenApiResponse(description="Invalid or expired refresh token"),
        },
        description="Refresh access token using a valid refresh token.",
    )
    def post(self, request, *args, **kwargs):
        """Refresh access token."""
        return super().post(request, *args, **kwargs)
