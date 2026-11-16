from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from assistant.core.formatting import truncate
from assistant.modules.prices.models import TrackedProduct
from assistant.modules.prices.money import drop_percent, format_brl
from assistant.modules.prices.rules import MIN_DROP_PERCENT, AlertKind
from assistant.modules.prices.service import CHECK_INTERVAL, PriceAlert

USAGE = (
    "Uso: /monitorar <link> [preço-alvo]\n\n"
    "Exemplos:\n"
    "/monitorar https://www.kabum.com.br/produto/123/ssd\n"
    "/monitorar https://www.kabum.com.br/produto/123/ssd 1.149,90\n\n"
    "Com alvo, aviso quando o preço chegar nele. Sem alvo, aviso quando cair "
    f"{MIN_DROP_PERCENT}% ou mais. Lojas suportadas: Kabum."
)

TITLE_MAX_LENGTH = 50
STOP_BUTTONS_PER_ROW = 5

CALLBACK_PATTERN = r"^prc:(l|n):(stop):(\d+)$"


class Source(StrEnum):
    LIST = "l"
    NOTIFICATION = "n"


class Action(StrEnum):
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class ButtonPress:
    source: Source
    action: Action
    product_id: int


def callback_data(source: Source, action: Action, product_id: int) -> str:
    return f"prc:{source}:{action}:{product_id}"


def parse_callback(groups: Sequence[str]) -> ButtonPress:
    source, action, product_id = groups
    return ButtonPress(Source(source), Action(action), int(product_id))


# ---- criação -----------------------------------------------------------------


def tracked_text(product: TrackedProduct) -> str:
    hours = int(CHECK_INTERVAL.total_seconds() // 3600)
    lines = [f"✅ Monitorando: {product.title}", _price_line(product)]

    if product.target_cents is None:
        lines.append(f"Sem alvo: aviso quando cair {MIN_DROP_PERCENT}% ou mais.")
    else:
        lines.append(f"🎯 Alvo: {format_brl(product.target_cents)}")
        if product.target_alerted:
            lines.append("🎉 Já está no alvo ou abaixo dele!")

    lines.append(f"Verifico a cada {hours}h, mais ou menos.")
    return "\n".join(lines)


def _price_line(product: TrackedProduct) -> str:
    price = format_brl(product.last_price_cents)
    if product.in_stock:
        return f"💰 Preço atual: {price}"
    return f"⚠️ Sem estoque (último preço: {price})"


# ---- listagem ----------------------------------------------------------------


def product_list_text(products: Sequence[TrackedProduct], max_products: int) -> str:
    if not products:
        return "Nenhum produto monitorado. Use /monitorar <link> [alvo]."

    lines = [f"📦 Produtos monitorados ({len(products)}/{max_products}):"]
    for number, product in enumerate(products, start=1):
        price = format_brl(product.last_price_cents)
        details = [price if product.in_stock else f"{price} (sem estoque)"]
        if product.lowest_price_cents < product.last_price_cents:
            details.append(f"menor {format_brl(product.lowest_price_cents)}")
        if product.target_cents is not None:
            details.append(f"alvo {format_brl(product.target_cents)}")

        lines.append("")
        lines.append(f"{number}. {truncate(product.title, TITLE_MAX_LENGTH)}")
        lines.append(f"   {' · '.join(details)}")
    return "\n".join(lines)


def product_list_keyboard(products: Sequence[TrackedProduct]) -> InlineKeyboardMarkup | None:
    if not products:
        return None
    buttons = [
        InlineKeyboardButton(
            f"🗑 {number}", callback_data=callback_data(Source.LIST, Action.STOP, product.id)
        )
        for number, product in enumerate(products, start=1)
    ]
    # Até 30 produtos: em linhas de 5, o teclado não fica gigante.
    rows = [
        buttons[i : i + STOP_BUTTONS_PER_ROW] for i in range(0, len(buttons), STOP_BUTTONS_PER_ROW)
    ]
    return InlineKeyboardMarkup(rows)


# ---- avisos ------------------------------------------------------------------


def alert_text(alert: PriceAlert) -> str:
    product = alert.product
    price = format_brl(product.last_price_cents)
    lines = [f"🛒 {product.title}"]

    for kind in alert.kinds:
        match kind:
            case AlertKind.TARGET_REACHED:
                target = format_brl(product.target_cents or 0)
                lines.append(f"🎯 Chegou no alvo de {target}! Agora: {price}")
            case AlertKind.PRICE_DROP:
                percent = drop_percent(alert.previous_cents, product.last_price_cents)
                previous = format_brl(alert.previous_cents)
                lines.append(f"📉 Caiu {percent}%: de {previous} para {price}")
            case AlertKind.BACK_IN_STOCK:
                lines.append(f"📦 Voltou ao estoque por {price}")
            case AlertKind.READ_FAILING:
                lines.append(
                    "⚠️ Não estou conseguindo ler o preço deste produto. "
                    "A página pode ter mudado ou saído do ar."
                )
            case AlertKind.STORE_BLOCKED:
                lines.append(
                    f"🚫 A {product.store} está recusando as consultas. "
                    "Vou pausar essa loja e tentar de novo mais tarde."
                )
    lines.append(product.url)
    return "\n".join(lines)


def alert_keyboard(alert: PriceAlert) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(
        "🗑 Parar de monitorar",
        callback_data=callback_data(Source.NOTIFICATION, Action.STOP, alert.product.id),
    )
    return InlineKeyboardMarkup([[button]])


def stopped_text(alert_message: str) -> str:
    """Texto do aviso depois de apertar "Parar": mantém o conteúdo e marca no fim."""
    return f"{alert_message}\n\n🗑 Parei de monitorar este produto."
