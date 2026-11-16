import re
from decimal import Decimal

# 1.149,90 / 1149,90 / 1.149 / 1149 (padrão brasileiro: vírgula decimal, ponto de milhar)
_BRAZILIAN = re.compile(r"^(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?$")
# 1149.90 / 1149.9 (ponto decimal, como no teclado americano)
_DOT_DECIMAL = re.compile(r"^\d+\.\d{1,2}$")

MAX_CENTS = 100_000_000_00


class MoneyParseError(ValueError):
    """Valor em reais inválido. A mensagem é mostrada ao usuário."""


def format_brl(cents: int) -> str:
    """114990 -> 'R$ 1.149,90'"""
    reais, rest = divmod(abs(cents), 100)
    sign = "-" if cents < 0 else ""
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{rest:02d}"


def parse_brl(text: str) -> int:
    """'1.149,90', '1149.90', '1149' ou 'R$ 1.149,90' -> 114990 (centavos)"""
    value = text.strip().removeprefix("R$").strip()

    if _DOT_DECIMAL.match(value):
        normalized = value
    elif _BRAZILIAN.match(value):
        normalized = value.replace(".", "").replace(",", ".")
    else:
        raise MoneyParseError(f'Não entendi o valor "{text}". Use, por exemplo, 1.149,90 ou 1149.')

    cents = int(Decimal(normalized) * 100)  # exato: no máximo 2 casas decimais
    if cents <= 0:
        raise MoneyParseError("O preço-alvo precisa ser maior que zero.")
    if cents > MAX_CENTS:
        raise MoneyParseError("Esse preço-alvo é alto demais.")
    return cents


def drop_percent(old_cents: int, new_cents: int) -> int:
    """Queda em % (inteiro, arredondado para baixo). Ex.: 10000 -> 9450 = 5"""
    if old_cents <= 0 or new_cents >= old_cents:
        return 0
    return (old_cents - new_cents) * 100 // old_cents
