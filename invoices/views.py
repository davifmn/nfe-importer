from collections import Counter
from datetime import date

from django.db import connection
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, JsonResponse
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import BaseParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Company, ImportLog, Invoice, InvoiceItem
from .nfe.documents import only_document_chars
from .nfe.parser import MAX_XML_BYTES
from .serializers import (
    CompanySerializer,
    ImportLogSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
)
from .services import ImportResult, import_nfe

MAX_FILES_PER_REQUEST = 100


class RawXMLParser(BaseParser):
    """Lets clients POST a single XML document as the request body."""

    media_type = "application/xml"

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read(MAX_XML_BYTES + 1)


class TextXMLParser(RawXMLParser):
    media_type = "text/xml"


class ImportView(APIView):
    """POST NF-e XML files (multipart field ``files``, repeatable) or one raw XML body."""

    parser_classes = [MultiPartParser, RawXMLParser, TextXMLParser]

    def post(self, request):
        if isinstance(request.data, bytes):
            uploads = [("body.xml", request.data)]
        else:
            uploads = [(f.name, f) for f in request.FILES.getlist("files")]
        if not uploads:
            return Response(
                {"detail": "Send XML files in the 'files' field, or an application/xml body."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(uploads) > MAX_FILES_PER_REQUEST:
            return Response(
                {"detail": f"At most {MAX_FILES_PER_REQUEST} files per request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        for name, upload in uploads:
            size = len(upload) if isinstance(upload, bytes) else upload.size
            if size > MAX_XML_BYTES:
                results.append(
                    ImportResult(name, "error", error_code="too_large", message="file too large")
                )
                continue
            content = upload if isinstance(upload, bytes) else upload.read()
            results.append(import_nfe(content, name))

        summary = Counter(r.status for r in results)
        if summary["created"]:
            code = status.HTTP_201_CREATED
        elif summary["error"] == len(results):
            code = status.HTTP_422_UNPROCESSABLE_ENTITY
        else:
            code = status.HTTP_200_OK
        return Response(
            {"summary": dict(summary), "results": [r.as_dict() for r in results]}, status=code
        )


class InvoiceFilters(serializers.Serializer):
    issuer = serializers.CharField(required=False)
    recipient = serializers.CharField(required=False)
    issued_from = serializers.DateField(required=False)
    issued_to = serializers.DateField(required=False)
    min_total = serializers.DecimalField(max_digits=15, decimal_places=2, required=False)
    max_total = serializers.DecimalField(max_digits=15, decimal_places=2, required=False)
    ncm = serializers.RegexField(r"^\d{2,8}$", required=False)
    status_code = serializers.IntegerField(required=False)


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """List, filter and inspect imported invoices. Looked up by access key."""

    lookup_field = "access_key"
    lookup_value_regex = "[0-9A-Z]{44}"

    def get_serializer_class(self):
        return InvoiceDetailSerializer if self.action == "retrieve" else InvoiceListSerializer

    def get_queryset(self):
        # select_related + annotate keep the list at a constant number of queries
        # (see tests/test_api.py::test_invoice_list_has_no_n_plus_one).
        qs = (
            Invoice.objects.select_related("issuer", "recipient")
            .annotate(item_count=Count("items"))
            # GROUP BY queries ignore Meta.ordering, so order explicitly for stable pages.
            .order_by("-issue_date", "-number", "-id")
        )
        if self.action == "retrieve":
            return qs.prefetch_related("items")
        if self.action != "list":
            return qs

        filters = InvoiceFilters(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        f = filters.validated_data
        if "issuer" in f:
            qs = qs.filter(issuer__document=only_document_chars(f["issuer"]))
        if "recipient" in f:
            qs = qs.filter(recipient__document=only_document_chars(f["recipient"]))
        if "issued_from" in f:
            qs = qs.filter(issue_date__gte=f["issued_from"])
        if "issued_to" in f:
            qs = qs.filter(issue_date__lte=f["issued_to"])
        if "min_total" in f:
            qs = qs.filter(invoice_total__gte=f["min_total"])
        if "max_total" in f:
            qs = qs.filter(invoice_total__lte=f["max_total"])
        if "status_code" in f:
            qs = qs.filter(status_code=f["status_code"])
        if "ncm" in f:
            qs = qs.filter(
                id__in=InvoiceItem.objects.filter(ncm__startswith=f["ncm"]).values("invoice_id")
            )
        return qs

    @action(detail=True, methods=["get"])
    def xml(self, request, access_key=None):
        """The original XML exactly as it was imported."""
        invoice = self.get_object()
        response = HttpResponse(invoice.xml, content_type="application/xml; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="NFe{invoice.access_key}.xml"'
        return response


class CompanyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CompanySerializer

    def get_queryset(self):
        qs = Company.objects.annotate(
            invoices_issued=Count("issued_invoices"),
            total_issued=Sum("issued_invoices__invoice_total"),
        ).order_by("name", "id")
        params = self.request.query_params
        if params.get("state"):
            qs = qs.filter(state=params["state"].upper())
        if params.get("search"):
            term = params["search"]
            qs = qs.filter(
                Q(name__icontains=term)
                | Q(trade_name__icontains=term)
                | Q(document=only_document_chars(term))
            )
        return qs


class ImportLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ImportLogSerializer

    def get_queryset(self):
        qs = ImportLog.objects.all()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs


class ReportFilters(serializers.Serializer):
    year = serializers.IntegerField(required=False, min_value=2006, max_value=2100)
    issuer = serializers.CharField(required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=10)


def _report_filters(request) -> dict:
    filters = ReportFilters(data=request.query_params)
    filters.is_valid(raise_exception=True)
    return filters.validated_data


def _invoice_scope(f: dict, prefix: str = "") -> Q:
    q = Q()
    if "year" in f:
        q &= Q(**{f"{prefix}issue_date__gte": date(f["year"], 1, 1)})
        q &= Q(**{f"{prefix}issue_date__lte": date(f["year"], 12, 31)})
    if "issuer" in f:
        q &= Q(**{f"{prefix}issuer__document": only_document_chars(f["issuer"])})
    return q


@api_view(["GET"])
def top_products(request):
    """Best-selling products by revenue, aggregated in the database."""
    f = _report_filters(request)
    rows = (
        InvoiceItem.objects.filter(_invoice_scope(f, "invoice__"))
        .values("product_code", "description", "ncm")
        .annotate(
            quantity=Sum("quantity"),
            revenue=Sum("total"),
            invoices=Count("invoice", distinct=True),
        )
        .order_by("-revenue", "product_code")[: f["limit"]]
    )
    return Response(list(rows))


@api_view(["GET"])
def monthly_totals(request):
    """Invoice count and value per fiscal month."""
    f = _report_filters(request)
    rows = (
        Invoice.objects.filter(_invoice_scope(f))
        .annotate(month=TruncMonth("issue_date"))
        .values("month")
        .annotate(invoices=Count("id"), total=Sum("invoice_total"), freight=Sum("freight_total"))
        .order_by("month")
    )
    return Response([{**r, "month": r["month"].strftime("%Y-%m")} for r in rows])


@api_view(["GET"])
def sales_by_state(request):
    """Where the goods went: totals per recipient state (CPF consumers without UF excluded)."""
    f = _report_filters(request)
    rows = (
        Invoice.objects.filter(_invoice_scope(f), recipient__isnull=False)
        .exclude(recipient__state="")
        .values(state=F("recipient__state"))
        .annotate(invoices=Count("id"), total=Sum("invoice_total"))
        .order_by("-total")
    )
    return Response(list(rows))


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok", "database": connection.vendor})
