# nfe-importer

[![CI](https://github.com/davifmn/nfe-importer/actions/workflows/ci.yml/badge.svg)](https://github.com/davifmn/nfe-importer/actions/workflows/ci.yml)

A Django REST API that imports Brazilian electronic invoices (**NF-e**, layout 4.00) from XML,
validates them beyond the schema, stores them in **MySQL** (or PostgreSQL/SQLite) and serves
filtered listings and sales reports.

Companies receive dozens or thousands of NF-e XML files a month from suppliers. They have to
archive them (the XML is the legal record) and they want the data out of them: who sold what,
for how much, and when. This service does that:

```sh
curl -H "Authorization: Token $TOKEN" -F files=@nota1.xml -F files=@nota2.xml \
     http://localhost:8000/api/imports/
```

```json
{
  "summary": {"created": 1, "duplicate": 1},
  "results": [
    {"filename": "nota1.xml", "status": "created", "access_key": "3126...", "invoice_id": 1},
    {"filename": "nota2.xml", "status": "duplicate", "access_key": "3126...", "invoice_id": 1}
  ]
}
```

## What gets validated

`invoices/nfe/parser.py` turns the XML into dataclasses and refuses anything inconsistent.
Each rejection carries a stable `error_code`:

| Check | `error_code` |
|---|---|
| XML with a DTD or entity declarations, e.g. XXE `file:///etc/passwd` or "billion laughs" (parsed with **defusedxml**) | `unsafe_xml` |
| Malformed XML, wrong root element, layout other than 4.00, file over 2 MiB | `malformed_xml`, `not_nfe`, `unsupported_version`, `too_large` |
| **Access key (chave de acesso) check digit**, modulo 11 with weights 2–9 | `invalid_access_key` |
| Every field encoded in the 44-character key (state, year/month, issuer CNPJ, model, series, number, emission type, random code, DV) must match the invoice body | `key_mismatch` |
| **CNPJ / CPF check digits** of issuer and recipient, including the **alphanumeric CNPJ** the Receita Federal started issuing in July 2026 | `invalid_cnpj`, `invalid_cpf` |
| The sum of the items must equal the declared products total (`ICMSTot/vProd`) | `total_mismatch` |
| The SEFAZ authorization protocol (`protNFe`) must refer to the same key | `protocol_mismatch` |
| Missing fields, non-numeric quantities, dates without a UTC offset | `missing_field`, `invalid_number`, `invalid_date` |

The check-digit code is tested against the worked example in the official *Manual de
Orientação do Contribuinte*, the classic CNPJ/CPF examples and the Receita's alphanumeric example
(`12.ABC.345/01DE-35`). The XML signature is **not** verified, because that needs the ICP-Brasil
certificate chain.

Importing is **idempotent**: the same file twice gives `duplicate`. Two concurrent workers racing
on the same key are handled through the database's unique constraint. A *different* key that
reuses an issuer's series and number is reported as `number_conflict`. Every attempt, including
failures, is written to an `ImportLog`.

## API

All endpoints need a token (`POST /api/auth/token/` with username/password), except `/health/`.

| Method & path | Description |
|---|---|
| `POST /api/imports/` | multipart `files` (up to 100) **or** a raw `application/xml` body. 201 if anything was created, 200 if only duplicates, 422 if everything failed. |
| `GET /api/invoices/` | Paginated list. Filters: `issuer`, `recipient` (CNPJ/CPF, formatted or not), `issued_from`, `issued_to`, `min_total`, `max_total`, `ncm` (prefix), `status_code`. |
| `GET /api/invoices/{access_key}/` | Invoice with items |
| `GET /api/invoices/{access_key}/xml/` | The original XML, byte for byte |
| `GET /api/companies/` | Issuers/recipients with number and value of invoices issued; `?state=`, `?search=`. CPFs are masked (LGPD). |
| `GET /api/reports/top-products/` | Revenue, quantity and invoice count per product; `?year=`, `?issuer=`, `?limit=` |
| `GET /api/reports/monthly/` | Invoices and value per fiscal month |
| `GET /api/reports/by-state/` | Totals per recipient state |
| `GET /api/import-logs/` | Import history; `?status=error` |

Money is always serialized as a decimal string (`"3687.00"`), never as a float.

## Design notes

- **Reports run in the database.** `values().annotate(Sum, Count)` produce a single `GROUP BY` query. The list endpoint uses `select_related` and an annotated item count, so it runs a constant number of queries however many invoices a page has. Tests enforce this with `django_assert_max_num_queries`.
- **Fiscal month without time zone tables.** An invoice issued at 23:30 on 31 October in Brasília is already November in UTC. The issuer's local date is stored in `issue_date`, and monthly reports group on that column. Reports are fiscally correct and don't depend on MySQL's time zone tables being loaded.
- **MySQL specifics:** `utf8mb4` everywhere (company names have accents), strict SQL mode, Decimal columns sized for NF-e values (`quantity` 4 decimal places, `unit_price` 10, as in the layout).
- **Original XML kept** with its SHA-256, because the XML is the legal document and must be archived.

## Running it

With Docker (MySQL 8.4 + gunicorn):

```sh
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py drf_create_token <user>
docker compose exec web python manage.py import_nfe samples/
```

Locally with SQLite:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python manage.py migrate
python manage.py generate_sample_nfe samples/ --count 50   # fictitious NF-e files
python manage.py import_nfe samples/
python manage.py runserver
```

Point it at MySQL with `DB_ENGINE=mysql DB_HOST=... DB_NAME=... DB_USER=... DB_PASSWORD=...`
(`pip install -e ".[mysql]"`), or at PostgreSQL with `DB_ENGINE=postgresql`.

## Tests

```sh
pytest
```

CI runs the suite on SQLite (Python 3.12 and 3.13) and against a real **MySQL 8.4** service.
It then builds the Docker image, starts the stack with `docker compose` and imports the sample
files through the HTTP API.

## Sample data

`samples/` and `manage.py generate_sample_nfe` produce **fictitious** NF-e files: coffee roasters
selling green and roasted beans (NCM 0901.11.10 / 0901.21.00) to cafés and consumers, in the
homologation environment (`tpAmb=2`). CNPJs and CPFs have random bases with computed check
digits, so they pass validation without belonging to anyone. One buyer uses an alphanumeric
CNPJ.

## License

MIT
