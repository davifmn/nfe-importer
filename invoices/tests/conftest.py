from datetime import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from invoices.nfe.samples import BRT, SampleCompany, SampleItem, build_nfe_xml

ISSUER = SampleCompany("11222333000181", "Torrefação Teste Ltda", "Teste", "Belo Horizonte", "MG")
BUYER = SampleCompany("12ABC34501DE35", "Cafeteria Alfanumérica Ltda", "Alfa", "São Paulo", "SP")
ROASTED = SampleItem(
    "TOR-1KG", "CAFE TORRADO EM GRAOS 1KG", "09012100", Decimal("3"), Decimal("129.00"), "KG"
)
GREEN = SampleItem(
    "CRU-SC", "CAFE CRU EM GRAO SC 60KG", "09011110", Decimal("2"), Decimal("1650.00"), "SC"
)


def make_xml(number=1, *, recipient=BUYER, items=(ROASTED, GREEN), when=None, **kwargs) -> bytes:
    return build_nfe_xml(
        ISSUER,
        recipient,
        list(items),
        number=number,
        issued_at=when or datetime(2026, 10, 15, 14, 30, tzinfo=BRT),
        **kwargs,
    )


@pytest.fixture
def xml():
    return make_xml()


@pytest.fixture
def api(db):
    user = get_user_model().objects.create_user("analyst", password="s3cret-pass")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client
