"""
Serializers for data processing and upload management.
"""

from rest_framework import serializers
from .models import Upload, ColumnMapping, RawTransaction, DataUpdate


class UploadSerializer(serializers.ModelSerializer):
    """
    Serializer for CSV upload records.

    Handles file upload metadata, processing status, and statistics.
    """

    company_name = serializers.CharField(source='company.name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Upload
        fields = [
            'id',
            'company',
            'company_name',
            'user',
            'user_email',
            'filename',
            'file_size',
            'status',
            'column_mappings',
            'original_rows',
            'processed_rows',
            'updated_rows',
            'error_rows',
            'error_message',
            'error_details',
            'progress_percentage',
            'created_at',
            'started_at',
            'completed_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'status',
            'original_rows',
            'processed_rows',
            'updated_rows',
            'error_rows',
            'error_message',
            'error_details',
            'progress_percentage',
            'created_at',
            'started_at',
            'completed_at',
        ]


class UploadCreateSerializer(serializers.Serializer):
    """
    Serializer for creating new CSV uploads.

    Validates file upload requests and column mappings.
    """

    company = serializers.IntegerField(required=True)
    file = serializers.FileField(required=True)
    column_mappings = serializers.CharField(required=True)

    def validate_column_mappings(self, value):
        """
        Parse and validate column mappings.

        Accepts either JSON string or dict.
        """
        import json

        # If already a dict, use it
        if isinstance(value, dict):
            mappings = value
        else:
            # Try to parse as JSON string
            try:
                mappings = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                raise serializers.ValidationError("Column mappings must be valid JSON.")

        if not isinstance(mappings, dict):
            raise serializers.ValidationError("Column mappings must be a dictionary.")

        # Required fields from COLUMN_SCHEMA
        required_fields = [
            'transaction_id',
            'transaction_date',
            'product_id',
            'quantity',
            'price_total',
        ]

        mapped_fields = set(mappings.values())
        missing_fields = [f for f in required_fields if f not in mapped_fields]

        if missing_fields:
            raise serializers.ValidationError(
                f"Missing required field mappings: {', '.join(missing_fields)}"
            )

        return mappings

    def validate_file(self, value):
        """
        Validate uploaded file.

        Checks:
        - File extension is .csv
        - File size is within limits (100MB max)
        - File is not empty
        """
        if not value.name.endswith('.csv'):
            raise serializers.ValidationError("Only CSV files are allowed.")

        # Check file size (100MB = 104857600 bytes)
        if value.size > 104857600:
            raise serializers.ValidationError("File size cannot exceed 100MB.")

        if value.size == 0:
            raise serializers.ValidationError("Uploaded file is empty.")

        return value

    def validate_company(self, value):
        """
        Validate company ID exists and user has upload permission.
        """
        from apps.companies.models import Company, UserCompany

        request = self.context.get('request')
        if not request or not request.user:
            raise serializers.ValidationError("Authentication required.")

        # Check if company exists
        try:
            company = Company.objects.get(id=value, is_active=True)
        except Company.DoesNotExist:
            raise serializers.ValidationError("Company not found.")

        # Check if user has upload permission for this company
        user_company = UserCompany.objects.filter(
            user=request.user,
            company=company
        ).first()

        if not user_company:
            raise serializers.ValidationError("You do not have access to this company.")

        if not user_company.can_upload:
            raise serializers.ValidationError("You do not have upload permission for this company.")

        return value


class ColumnMappingSerializer(serializers.ModelSerializer):
    """
    Serializer for saved column mappings.

    Allows users to save and reuse column mapping configurations.
    """

    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = ColumnMapping
        fields = [
            'id',
            'company',
            'company_name',
            'mapping_name',
            'mappings',
            'formats',
            'defaults',
            'created_at',
            'updated_at',
            'is_default',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_mappings(self, value):
        """Validate mappings structure matches COLUMN_SCHEMA."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Mappings must be a dictionary.")

        # At least one mapping required
        if not value:
            raise serializers.ValidationError("At least one column mapping required.")

        return value


class RawTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for raw transaction data.

    Read-only serializer for viewing processed transaction data.
    """

    company_name = serializers.CharField(source='company.name', read_only=True)
    upload_filename = serializers.CharField(source='upload.filename', read_only=True)

    class Meta:
        model = RawTransaction
        fields = [
            'id',
            'company',
            'company_name',
            'upload',
            'upload_filename',
            'data',
            'transaction_date',
            'transaction_id',
            'product_id',
            'customer_id',
            'category',
            'quantity',
            'price_total',
            'cost_total',
            'processed_at',
        ]
        read_only_fields = fields  # All fields are read-only


class DataUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for data update tracking records.

    Provides transparency about data modifications from uploads.
    """

    company_name = serializers.CharField(source='company.name', read_only=True)
    upload_filename = serializers.CharField(source='upload.filename', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    net_change = serializers.IntegerField(read_only=True)

    class Meta:
        model = DataUpdate
        fields = [
            'id',
            'company',
            'company_name',
            'upload',
            'upload_filename',
            'user',
            'user_email',
            'period',
            'period_type',
            'rows_before',
            'rows_after',
            'rows_updated',
            'rows_added',
            'rows_deleted',
            'net_change',
            'changes_summary',
            'timestamp',
        ]
        read_only_fields = fields  # All fields are read-only
