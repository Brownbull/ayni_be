"""
Company management API views for AYNI platform.

This module provides REST API endpoints for company CRUD operations,
user-company relationship management, and permission-based access control.
"""

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import Company, UserCompany
from .serializers import (
    CompanySerializer,
    CompanyCreateSerializer,
    UserCompanySerializer
)


class CompanyListCreateView(generics.ListCreateAPIView):
    """
    List all companies for authenticated user or create a new company.

    GET: Returns all companies where user has access
    POST: Creates new company and assigns user as owner
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        """Use different serializers for create vs list."""
        if self.request.method == 'POST':
            return CompanyCreateSerializer
        return CompanySerializer

    def get_queryset(self):
        """
        Return companies where user has active access.

        Filters:
        - is_active=True (exclude soft-deleted companies)
        - user has UserCompany relationship
        """
        user = self.request.user

        # Get companies where user has access
        user_company_ids = UserCompany.objects.filter(
            user=user,
            is_active=True
        ).values_list('company_id', flat=True)

        return Company.objects.filter(
            id__in=user_company_ids,
            is_active=True
        ).order_by('-created_at')

    @extend_schema(
        summary="List all companies for current user",
        description="Returns all companies where the authenticated user has access",
        responses={
            200: CompanySerializer(many=True),
            401: OpenApiResponse(description="Unauthorized"),
        }
    )
    def get(self, request, *args, **kwargs):
        """List companies for authenticated user."""
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a new company",
        description="Creates a new company and assigns the current user as owner",
        request=CompanyCreateSerializer,
        responses={
            201: CompanySerializer,
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Unauthorized"),
        }
    )
    def post(self, request, *args, **kwargs):
        """Create new company."""
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        """
        Create company and return full serialized data.

        The CompanyCreateSerializer handles creating the UserCompany relationship.
        """
        company = serializer.save()

        # Return full company data with user context
        return company


class CompanyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a company.

    GET: Retrieve company details
    PATCH/PUT: Update company (requires can_manage_company permission)
    DELETE: Soft delete company (requires owner role)
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CompanySerializer
    lookup_field = 'id'

    def get_queryset(self):
        """Return companies where user has access."""
        user = self.request.user

        user_company_ids = UserCompany.objects.filter(
            user=user,
            is_active=True
        ).values_list('company_id', flat=True)

        return Company.objects.filter(
            id__in=user_company_ids,
            is_active=True
        )

    def check_company_permission(self, company, permission):
        """
        Check if user has specific permission for company.

        Args:
            company: Company instance
            permission: Permission string (e.g., 'can_manage_company')

        Returns:
            bool: True if user has permission

        Raises:
            PermissionDenied: If user lacks permission
        """
        from rest_framework.exceptions import PermissionDenied

        user = self.request.user

        try:
            user_company = UserCompany.objects.get(
                user=user,
                company=company,
                is_active=True
            )

            if not user_company.has_permission(permission):
                raise PermissionDenied(
                    f"You don't have permission to perform this action on this company"
                )

            return True

        except UserCompany.DoesNotExist:
            raise PermissionDenied("You don't have access to this company")

    @extend_schema(
        summary="Get company details",
        description="Retrieve detailed information about a specific company",
        responses={
            200: CompanySerializer,
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Company not found"),
        }
    )
    def get(self, request, *args, **kwargs):
        """Retrieve company details."""
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update company",
        description="Update company details (requires can_manage_company permission)",
        request=CompanySerializer,
        responses={
            200: CompanySerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Company not found"),
        }
    )
    def patch(self, request, *args, **kwargs):
        """Partially update company."""
        company = self.get_object()
        self.check_company_permission(company, 'can_manage_company')
        return super().patch(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        """Fully update company."""
        company = self.get_object()
        self.check_company_permission(company, 'can_manage_company')
        return super().put(request, *args, **kwargs)

    @extend_schema(
        summary="Delete company",
        description="Soft delete a company (requires owner role)",
        responses={
            204: OpenApiResponse(description="Company deleted"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Company not found"),
        }
    )
    def delete(self, request, *args, **kwargs):
        """
        Soft delete company.

        Only owners can delete companies.
        """
        company = self.get_object()

        # Check if user is owner
        user = request.user
        try:
            user_company = UserCompany.objects.get(
                user=user,
                company=company,
                is_active=True
            )

            if user_company.role != 'owner':
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Only company owners can delete companies")

        except UserCompany.DoesNotExist:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You don't have access to this company")

        # Perform soft delete
        company.soft_delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class CompanyUsersView(APIView):
    """
    Manage users for a specific company.

    GET: List all users with access to company
    POST: Add user to company with role
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List company users",
        description="Get all users with access to a specific company",
        parameters=[
            OpenApiParameter(
                name='company_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='Company ID'
            ),
        ],
        responses={
            200: UserCompanySerializer(many=True),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Company not found"),
        }
    )
    def get(self, request, company_id):
        """List all users for company."""
        user = request.user

        # Check if company exists and user has access
        try:
            company = Company.objects.get(id=company_id, is_active=True)
        except Company.DoesNotExist:
            return Response(
                {'error': 'Company not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verify user has access to company
        try:
            UserCompany.objects.get(
                user=user,
                company=company,
                is_active=True
            )
        except UserCompany.DoesNotExist:
            return Response(
                {'error': 'You don\'t have access to this company'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get all users for company
        user_companies = UserCompany.objects.filter(
            company=company,
            is_active=True
        ).select_related('user', 'company')

        serializer = UserCompanySerializer(user_companies, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Add user to company",
        description="Add a user to company with specific role (requires can_manage_users permission)",
        parameters=[
            OpenApiParameter(
                name='company_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='Company ID'
            ),
        ],
        request=UserCompanySerializer,
        responses={
            201: UserCompanySerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Company not found"),
        }
    )
    def post(self, request, company_id):
        """Add user to company with role."""
        # Add company_id to request data
        data = request.data.copy()
        data['company'] = company_id

        serializer = UserCompanySerializer(data=data, context={'request': request})

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserCompanyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Manage specific user-company relationship.

    GET: Retrieve relationship details
    PATCH/PUT: Update user role/permissions
    DELETE: Remove user from company
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UserCompanySerializer
    lookup_field = 'id'

    def get_queryset(self):
        """Return user-company relationships where requester has management access."""
        user = self.request.user

        # Get companies where user can manage users
        manageable_companies = UserCompany.objects.filter(
            user=user,
            is_active=True
        ).filter(
            Q(role='owner') | Q(role='admin') | Q(permissions__can_manage_users=True)
        ).values_list('company_id', flat=True)

        return UserCompany.objects.filter(
            company_id__in=manageable_companies
        ).select_related('user', 'company')

    @extend_schema(
        summary="Get user-company relationship",
        responses={
            200: UserCompanySerializer,
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Relationship not found"),
        }
    )
    def get(self, request, *args, **kwargs):
        """Retrieve user-company relationship."""
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update user-company relationship",
        request=UserCompanySerializer,
        responses={
            200: UserCompanySerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied"),
        }
    )
    def patch(self, request, *args, **kwargs):
        """Update user role/permissions."""
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        summary="Remove user from company",
        responses={
            204: OpenApiResponse(description="User removed"),
            403: OpenApiResponse(description="Permission denied"),
        }
    )
    def delete(self, request, *args, **kwargs):
        """
        Remove user from company (soft delete).

        Cannot remove last owner.
        """
        user_company = self.get_object()
        company = user_company.company

        # Check if removing last owner
        if user_company.role == 'owner':
            owner_count = UserCompany.objects.filter(
                company=company,
                role='owner',
                is_active=True
            ).count()

            if owner_count <= 1:
                return Response(
                    {'error': 'Cannot remove the last owner of a company'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Soft delete relationship
        user_company.is_active = False
        user_company.save(update_fields=['is_active'])

        return Response(status=status.HTTP_204_NO_CONTENT)
