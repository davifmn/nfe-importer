from collections import defaultdict
from datetime import datetime
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from invoices.models import Invoice
from invoices.nfe.samples import BRT, generate_batch
from invoices.services import import_nfe

from .conftest import make_xml

pytestmark = pytest.mark.django_db


def upload(name, content):
    return SimpleUploadedFile(name, content, content_type="text/xml")


@pytest.fixture
def batch():
    files = generate_batch(25, seed=7)
    for name, xml in files:
        assert import_nfe(xml, name).status == "created"
    return files


def test_authentication_is_required():
    assert APIClient().get("/api/invoices/").status_code == 401
    assert APIClient().get("/health/").status_code == 200


def test_multipart_upload_of_several_files(api):
    files = [upload(f"{n}.xml", make_xml(number=n)) for n in (1, 2, 3)] + [upload("x.xml", b"<x")]
    response = api.post("/api/imports/", {"files": files}, format="multipart")
    assert response.status_code == 201
    assert response.json()["summary"] == {"created": 3, "error": 1}
    errors = [r for r in response.json()["results"] if r["status"] == "error"]
    assert errors[0]["filename"] == "x.xml" and errors[0]["error_code"] == "malformed_xml"


def test_raw_xml_body_upload_and_duplicate(api, xml):
    first = api.post("/api/imports/", xml, content_type="application/xml")
    again = api.post("/api/imports/", xml, content_type="application/xml")
    assert first.status_code == 201
    assert again.status_code == 200 and again.json()["summary"] == {"duplicate": 1}


def test_only_errors_is_unprocessable(api):
    response = api.post("/api/imports/", b"<nope/>", content_type="application/xml")
    assert response.status_code == 422


def test_upload_without_files(api):
    assert api.post("/api/imports/", {}, format="multipart").status_code == 400


def test_invoice_detail_and_original_xml(api, xml):
    key = import_nfe(xml).access_key
    detail = api.get(f"/api/invoices/{key}/").json()
    assert detail["invoice_total"] == "3687.00"  # money as string, never float
    assert [i["ncm"] for i in detail["items"]] == ["09012100", "09011110"]
    raw = api.get(f"/api/invoices/{key}/xml/")
    assert raw["Content-Type"].startswith("application/xml")
    assert raw.content == xml


def test_invoice_list_has_no_n_plus_one(api, batch, django_assert_max_num_queries):
    # auth token + count + page = constant, whatever the number of invoices.
    with django_assert_max_num_queries(4):
        response = api.get("/api/invoices/?page_size=100")
    body = response.json()
    assert body["count"] == 25
    assert all(row["item_count"] >= 1 for row in body["results"])


def test_invoice_detail_query_count(api, batch, django_assert_max_num_queries):
    key = Invoice.objects.first().access_key
    with django_assert_max_num_queries(3):
        api.get(f"/api/invoices/{key}/")


def test_invoice_filters(api, batch):
    invoices = list(Invoice.objects.select_related("issuer"))
    issuer = invoices[0].issuer.document
    by_issuer = api.get(f"/api/invoices/?issuer={issuer}&page_size=100").json()
    assert by_issuer["count"] == sum(1 for i in invoices if i.issuer.document == issuer)

    june = api.get("/api/invoices/?issued_from=2026-06-01&issued_to=2026-06-30").json()
    assert june["count"] == sum(1 for i in invoices if i.issue_date.month == 6)

    green = api.get("/api/invoices/?ncm=090111&page_size=100").json()
    expected = Invoice.objects.filter(items__ncm="09011110").distinct().count()
    assert green["count"] == expected

    assert api.get("/api/invoices/?min_total=abc").status_code == 400


def test_top_products_report_matches_python(api, batch):
    rows = api.get("/api/reports/top-products/?year=2026&limit=3").json()
    expected = defaultdict(Decimal)
    for invoice in Invoice.objects.prefetch_related("items"):
        for item in invoice.items.all():
            expected[item.product_code] += item.total
    best = sorted(expected.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    assert [(r["product_code"], Decimal(r["revenue"])) for r in rows] == best


def test_monthly_report_uses_the_fiscal_date(api):
    late_night = datetime(2026, 10, 31, 23, 30, tzinfo=BRT)  # already November in UTC
    import_nfe(make_xml(number=1, when=late_night))
    import_nfe(make_xml(number=2, when=datetime(2026, 11, 2, 10, 0, tzinfo=BRT)))
    rows = api.get("/api/reports/monthly/").json()
    assert [(r["month"], r["invoices"]) for r in rows] == [("2026-10", 1), ("2026-11", 1)]


def test_sales_by_state(api, batch):
    rows = api.get("/api/reports/by-state/").json()
    assert rows and {"state", "invoices", "total"} <= rows[0].keys()
    totals = [Decimal(r["total"]) for r in rows]
    assert totals == sorted(totals, reverse=True)


def test_companies_are_annotated_and_cpfs_masked(api):
    import_nfe(make_xml(number=1, recipient="52998224725"))
    companies = {c["kind"]: c for c in api.get("/api/companies/").json()["results"]}
    assert companies["cnpj"]["invoices_issued"] == 1
    assert companies["cnpj"]["formatted_document"] == "11.222.333/0001-81"
    assert companies["cpf"]["formatted_document"] == "***.982.247-**"


def test_import_logs_endpoint(api):
    import_nfe(b"<bad", "bad.xml")
    logs = api.get("/api/import-logs/?status=error").json()["results"]
    assert logs[0]["filename"] == "bad.xml"
