"""
Processing URLs

Endpoints for CSV upload, processing, and data management.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"uploads", views.UploadViewSet, basename="upload")
router.register(r"mappings", views.ColumnMappingViewSet, basename="mapping")
router.register(r"transactions", views.RawTransactionViewSet, basename="transaction")
router.register(r"updates", views.DataUpdateViewSet, basename="dataupdate")

urlpatterns = [
    path("", include(router.urls)),
]
