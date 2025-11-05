"""
Companies URLs for AYNI platform.

API endpoints for company management and user-company relationships.
"""
from django.urls import path
from .views import (
    CompanyListCreateView,
    CompanyDetailView,
    CompanyUsersView,
    UserCompanyDetailView
)

app_name = 'companies'

urlpatterns = [
    # Company CRUD
    path('', CompanyListCreateView.as_view(), name='company-list-create'),
    path('<int:id>/', CompanyDetailView.as_view(), name='company-detail'),

    # Company users management
    path('<int:company_id>/users/', CompanyUsersView.as_view(), name='company-users'),
    path('user-companies/<int:id>/', UserCompanyDetailView.as_view(), name='user-company-detail'),
]
