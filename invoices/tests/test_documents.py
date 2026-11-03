import pytest

from invoices.nfe.documents import (
    access_key_check_digit,
    build_access_key,
    format_cnpj,
    is_valid_access_key,
    is_valid_cnpj,
    is_valid_cpf,
    split_access_key,
)


def test_access_key_example_from_the_official_manual():
    # Worked example from the NF-e Manual de Orientação do Contribuinte: DV = 5.
    assert access_key_check_digit("5206043300991100250655012000000780026730161") == 5
    assert is_valid_access_key("52060433009911002506550120000007800267301615")
    assert not is_valid_access_key("52060433009911002506550120000007800267301614")


@pytest.mark.parametrize("key", ["", "123", "5206043300991100250655012000000780026730161X"])
def test_malformed_access_keys(key):
    assert not is_valid_access_key(key)


def test_build_and_split_round_trip():
    key = build_access_key(
        state_code="31",
        year_month="2610",
        cnpj="11222333000181",
        model="55",
        series=1,
        number=4321,
        emission_type=1,
        random_code="87654321",
    )
    assert is_valid_access_key(key)
    parts = split_access_key(key)
    assert parts["cnpj"] == "11222333000181"
    assert parts["number"] == "000004321"
    assert parts["random_code"] == "87654321"


@pytest.mark.parametrize(
    ("cnpj", "valid"),
    [
        ("11.222.333/0001-81", True),
        ("11222333000181", True),
        ("11222333000182", False),
        ("00000000000000", False),
        ("1122233300018", False),
        # Alphanumeric CNPJ (issued since July 2026); example published by the Receita Federal.
        ("12.ABC.345/01DE-35", True),
        ("12ABC34501DE34", False),
        ("12abc34501de35", True),
    ],
)
def test_cnpj(cnpj, valid):
    assert is_valid_cnpj(cnpj) is valid


@pytest.mark.parametrize(
    ("cpf", "valid"),
    [("529.982.247-25", True), ("52998224724", False), ("11111111111", False), ("123", False)],
)
def test_cpf(cpf, valid):
    assert is_valid_cpf(cpf) is valid


def test_format_cnpj():
    assert format_cnpj("11222333000181") == "11.222.333/0001-81"
