"""Importing NF-e documents into the database."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.db import IntegrityError, transaction

from .models import Company, ImportLog, Invoice, InvoiceItem
from .nfe.parser import NFeError, Party, parse_nfe


@dataclass(frozen=True)
class ImportResult:
    filename: str
    status: str  # created | duplicate | error
    access_key: str = ""
    invoice_id: int | None = None
    error_code: str = ""
    message: str = ""

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in ("", None)}


def _upsert_company(party: Party) -> Company:
    company, created = Company.objects.get_or_create(
        document=party.document,
        defaults={
            "kind": party.kind,
            "name": party.name,
            "trade_name": party.trade_name,
            "city": party.city,
            "state": party.state,
            "state_registration": party.state_registration,
        },
    )
    if not created:
        # Keep the registry current: names and addresses change over time.
        changed = False
        for field in ("name", "trade_name", "city", "state", "state_registration"):
            value = getattr(party, field)
            if value and getattr(company, field) != value:
                setattr(company, field, value)
                changed = True
        if changed:
            company.save()
    return company


def import_nfe(xml: bytes, filename: str = "upload.xml") -> ImportResult:
    """Parse, validate and store one NF-e. Safe to call twice with the same file."""
    digest = hashlib.sha256(xml).hexdigest()
    try:
        parsed = parse_nfe(xml)
    except NFeError as exc:
        return _log(ImportResult(filename, "error", error_code=exc.code, message=str(exc)))

    existing = Invoice.objects.filter(access_key=parsed.access_key).only("id").first()
    if existing:
        return _log(
            ImportResult(filename, "duplicate", parsed.access_key, existing.id),
            invoice=existing,
        )

    try:
        with transaction.atomic():
            invoice = Invoice.objects.create(
                access_key=parsed.access_key,
                model=parsed.model,
                series=parsed.series,
                number=parsed.number,
                issued_at=parsed.issued_at,
                issue_date=parsed.issue_date,
                operation_nature=parsed.operation_nature,
                direction=parsed.direction,
                issuer=_upsert_company(parsed.issuer),
                recipient=_upsert_company(parsed.recipient) if parsed.recipient else None,
                products_total=parsed.products_total,
                discount_total=parsed.discount_total,
                freight_total=parsed.freight_total,
                invoice_total=parsed.invoice_total,
                authorization_protocol=parsed.authorization_protocol,
                status_code=parsed.status_code,
                xml_sha256=digest,
                xml=xml.decode("utf-8"),
            )
            InvoiceItem.objects.bulk_create(
                InvoiceItem(invoice=invoice, **item.__dict__) for item in parsed.items
            )
    except IntegrityError:
        # Another worker imported the same key between our check and the insert.
        winner = Invoice.objects.filter(access_key=parsed.access_key).first()
        if winner is None:
            # Same issuer, model, series and number but a different access key.
            return _log(
                ImportResult(
                    filename,
                    "error",
                    parsed.access_key,
                    error_code="number_conflict",
                    message=(
                        f"issuer already has invoice {parsed.number}/{parsed.series} "
                        "under a different access key"
                    ),
                )
            )
        return _log(
            ImportResult(filename, "duplicate", parsed.access_key, winner.id), invoice=winner
        )
    return _log(ImportResult(filename, "created", parsed.access_key, invoice.id), invoice=invoice)


def _log(result: ImportResult, invoice: Invoice | None = None) -> ImportResult:
    ImportLog.objects.create(
        filename=result.filename[:255],
        status=result.status,
        error_code=result.error_code,
        message=result.message,
        access_key=result.access_key,
        invoice=invoice,
    )
    return result
