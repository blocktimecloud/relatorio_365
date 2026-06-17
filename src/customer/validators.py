"""
Validação e formatação de CNPJ.
Armazenamos sempre o CNPJ limpo (14 dígitos) e formatamos apenas na exibição.
"""
import re

from core.exceptions.customer import InvalidCNPJException

_CNPJ_FIRST_WEIGHTS  = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_CNPJ_SECOND_WEIGHTS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def clean_cnpj(cnpj: str) -> str:
    """Remove tudo que não for dígito."""
    return re.sub(r"\D", "", cnpj or "")


def _check_digit(digits: str, weights: list[int]) -> int:
    total = sum(int(d) * w for d, w in zip(digits, weights))
    rest = total % 11
    return 0 if rest < 2 else 11 - rest


def validate_cnpj(cnpj: str) -> str:
    """
    Valida o CNPJ (formato + dígitos verificadores) e retorna o valor limpo
    (14 dígitos). Levanta InvalidCNPJException se for inválido.
    """
    digits = clean_cnpj(cnpj)

    if len(digits) != 14:
        raise InvalidCNPJException(cnpj, "deve conter 14 dígitos")

    if digits == digits[0] * 14:
        raise InvalidCNPJException(cnpj, "sequência de dígitos inválida")

    first  = _check_digit(digits[:12], _CNPJ_FIRST_WEIGHTS)
    second = _check_digit(digits[:13], _CNPJ_SECOND_WEIGHTS)

    if digits[12:] != f"{first}{second}":
        raise InvalidCNPJException(cnpj, "dígitos verificadores não conferem")

    return digits


def format_cnpj(cnpj: str) -> str:
    """Formata um CNPJ limpo como XX.XXX.XXX/XXXX-XX (apenas para exibição)."""
    d = clean_cnpj(cnpj)
    if len(d) != 14:
        return cnpj
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"