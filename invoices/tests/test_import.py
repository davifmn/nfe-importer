import pytest

from invoices.models import Company, ImportLog, Invoice
from invoices.services import import_nfe

from .conftest import ISSUER, make_xml

pytestmark = pytest.mark.django_db


def test_import_creates_invoice_items_and_companies(xml):
    result = import_nfe(xml, "a.xml")
    assert result.status == "created"
    invoice = Invoice.objects.get(access_key=result.access_key)
    assert invoice.items.count() == 2
    assert invoice.issuer.document == ISSUER.cnpj
    assert invoice.recipient.document == "12ABC34501DE35"
    assert Company.objects.count() == 2
    assert invoice.xml.encode() == xml  # kept byte-for-byte for audit
    assert ImportLog.objects.get().status == "created"


def test_import_is_idempotent(xml):
    first = import_nfe(xml, "a.xml")
    second = import_nfe(xml, "a-copy.xml")
    assert second.status == "duplicate"
    assert second.invoice_id == first.invoice_id
    assert Invoice.objects.count() == 1
    assert list(ImportLog.objects.values_list("status", flat=True)) == ["duplicate", "created"]


def test_invalid_files_are_logged_not_stored():
    result = import_nfe(b"<broken", "bad.xml")
    assert result.status == "error" and result.error_code == "malformed_xml"
    assert Invoice.objects.count() == 0
    log = ImportLog.objects.get()
    assert (log.filename, log.error_code) == ("bad.xml", "malformed_xml")


def test_same_number_with_a_different_key_is_a_conflict():
    import_nfe(make_xml(number=7, random_code="11111111"))
    result = import_nfe(make_xml(number=7, random_code="22222222"))
    assert result.status == "error"
    assert result.error_code == "number_conflict"
    assert Invoice.objects.count() == 1


def test_company_registry_is_updated(monkeypatch):
    import_nfe(make_xml(number=1))
    renamed = make_xml(number=2).replace(
        "Torrefação Teste Ltda".encode(), "Torrefação Teste S.A.".encode()
    )
    assert import_nfe(renamed).status == "created"
    assert Company.objects.get(document=ISSUER.cnpj).name == "Torrefação Teste S.A."
