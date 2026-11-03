from datetime import date
from decimal import Decimal

import pytest

from invoices.nfe.parser import MAX_XML_BYTES, NFeError, parse_nfe
from invoices.nfe.samples import generate_batch

from .conftest import BUYER, ISSUER, make_xml


def test_parses_a_distributed_nfe(xml):
    nfe = parse_nfe(xml)
    assert nfe.model == "55" and nfe.series == 1 and nfe.number == 1
    assert nfe.issue_date == date(2026, 10, 15)
    assert nfe.issuer.document == ISSUER.cnpj and nfe.issuer.state == "MG"
    assert nfe.recipient.document == BUYER.cnpj  # alphanumeric CNPJ
    assert [i.ncm for i in nfe.items] == ["09012100", "09011110"]
    assert nfe.products_total == Decimal("3687.00")
    assert nfe.invoice_total == Decimal("3687.00")
    assert nfe.status_code == 100 and nfe.authorization_protocol


def test_parses_a_bare_nfe_without_protocol():
    nfe = parse_nfe(make_xml(with_protocol=False))
    assert nfe.status_code is None and nfe.authorization_protocol == ""


def test_consumer_recipient_with_cpf():
    nfe = parse_nfe(make_xml(recipient="52998224725"))
    assert nfe.recipient.kind == "cpf"


def test_fiscal_date_uses_the_issuers_offset():
    from datetime import datetime

    from invoices.nfe.samples import BRT

    # 23:30 in Brasília is already the next day in UTC; the fiscal date must not move.
    nfe = parse_nfe(make_xml(when=datetime(2026, 10, 31, 23, 30, tzinfo=BRT)))
    assert nfe.issue_date == date(2026, 10, 31)


def test_every_generated_sample_is_valid():
    for _, xml in generate_batch(60, seed=1):
        parse_nfe(xml)


def tamper(xml: bytes, old: str, new: str, count: int = 1) -> bytes:
    assert old.encode() in xml, old
    return xml.replace(old.encode(), new.encode(), count)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        # Flip the access key check digit everywhere it appears.
        (
            lambda x, k: x.replace(k.encode(), (k[:-1] + str((int(k[-1]) + 1) % 10)).encode()),
            "invalid_access_key",
        ),
        # Body says invoice 2, key says invoice 1.
        (lambda x, k: tamper(x, "<nNF>1</nNF>", "<nNF>2</nNF>"), "key_mismatch"),
        # Issuer CNPJ with a wrong check digit (key changed accordingly would still fail DV).
        (
            lambda x, k: tamper(x, "<CNPJ>11222333000181</CNPJ>", "<CNPJ>11222333000182</CNPJ>"),
            "invalid_cnpj",
        ),
        # Item value no longer adds up to the declared products total.
        (
            lambda x, k: tamper(x, "<vProd>387.00</vProd>", "<vProd>380.00</vProd>"),
            "total_mismatch",
        ),
        (
            lambda x, k: tamper(x, f"<chNFe>{k}</chNFe>", f"<chNFe>{'1' * 44}</chNFe>"),
            "protocol_mismatch",
        ),
        (
            lambda x, k: tamper(x, 'infNFe versao="4.00"', 'infNFe versao="3.10"'),
            "unsupported_version",
        ),
        (lambda x, k: tamper(x, "-03:00</dhEmi>", "</dhEmi>"), "invalid_date"),
        (lambda x, k: tamper(x, "<qCom>3.0000</qCom>", "<qCom>three</qCom>"), "invalid_number"),
        (lambda x, k: tamper(x, "<xNome>Torrefação Teste Ltda</xNome>", ""), "missing_field"),
    ],
)
def test_validation_errors(xml, change, code):
    key = parse_nfe(xml).access_key
    with pytest.raises(NFeError) as exc:
        parse_nfe(change(xml, key))
    assert exc.value.code == code


def test_rejects_xxe():
    payload = b"""<?xml version="1.0"?>
<!DOCTYPE nfeProc [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><x>&xxe;</x></nfeProc>"""
    with pytest.raises(NFeError) as exc:
        parse_nfe(payload)
    assert exc.value.code == "unsafe_xml"


def test_rejects_billion_laughs():
    payload = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;">]>
<lolz>&lol2;</lolz>"""
    with pytest.raises(NFeError) as exc:
        parse_nfe(payload)
    assert exc.value.code == "unsafe_xml"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"<not-closed", "malformed_xml"),
        (b"<invoice xmlns='urn:other'/>", "not_nfe"),
        (b"x" * (MAX_XML_BYTES + 1), "too_large"),
    ],
)
def test_rejects_non_nfe_documents(payload, code):
    with pytest.raises(NFeError) as exc:
        parse_nfe(payload)
    assert exc.value.code == code


def test_rejects_invoice_without_items():
    with pytest.raises(NFeError) as exc:
        parse_nfe(make_xml(items=()))
    assert exc.value.code in {"no_items", "total_mismatch"}
