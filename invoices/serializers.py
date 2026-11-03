from rest_framework import serializers

from .models import Company, ImportLog, Invoice, InvoiceItem
from .nfe.documents import format_cnpj


class CompanySerializer(serializers.ModelSerializer):
    formatted_document = serializers.SerializerMethodField()
    invoices_issued = serializers.IntegerField(read_only=True, required=False)
    total_issued = serializers.DecimalField(
        max_digits=17, decimal_places=2, read_only=True, required=False
    )

    class Meta:
        model = Company
        fields = [
            "id",
            "document",
            "formatted_document",
            "kind",
            "name",
            "trade_name",
            "city",
            "state",
            "invoices_issued",
            "total_issued",
        ]

    def get_formatted_document(self, obj: Company) -> str:
        if obj.kind == Company.Kind.CNPJ:
            return format_cnpj(obj.document)
        return f"***.{obj.document[3:6]}.{obj.document[6:9]}-**"  # mask CPFs (LGPD)


class CompanySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "document", "name", "state"]


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = [
            "item_number",
            "product_code",
            "description",
            "ncm",
            "cfop",
            "unit",
            "quantity",
            "unit_price",
            "total",
        ]


class InvoiceListSerializer(serializers.ModelSerializer):
    issuer = CompanySummarySerializer(read_only=True)
    recipient = CompanySummarySerializer(read_only=True)
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "access_key",
            "model",
            "series",
            "number",
            "issue_date",
            "issuer",
            "recipient",
            "invoice_total",
            "status_code",
            "item_count",
        ]


class InvoiceDetailSerializer(InvoiceListSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)

    class Meta(InvoiceListSerializer.Meta):
        fields = InvoiceListSerializer.Meta.fields + [
            "issued_at",
            "operation_nature",
            "direction",
            "products_total",
            "discount_total",
            "freight_total",
            "authorization_protocol",
            "imported_at",
            "items",
        ]


class ImportLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportLog
        fields = ["id", "filename", "status", "error_code", "message", "access_key", "created_at"]
