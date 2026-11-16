import re
from datetime import UTC, datetime

from assistant.modules.prices import views
from assistant.modules.prices.models import TrackedProduct
from assistant.modules.prices.rules import AlertKind
from assistant.modules.prices.service import MAX_PRODUCTS, PriceAlert
from assistant.modules.prices.views import Action, ButtonPress, Source

URL = "https://www.kabum.com.br/produto/1/ssd"
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def make_product(product_id: int = 1, **kwargs: object) -> TrackedProduct:
    defaults: dict[str, object] = {
        "chat_id": 42,
        "url": URL,
        "store": "Kabum",
        "title": "SSD 1TB",
        "target_cents": None,
        "target_alerted": False,
        "last_price_cents": 50000,
        "lowest_price_cents": 50000,
        "in_stock": True,
        "last_checked_at": NOW,
        "next_check_at": NOW,
        "consecutive_failures": 0,
    }
    return TrackedProduct(id=product_id, **(defaults | kwargs))


def test_callback_data_round_trip() -> None:
    data = views.callback_data(Source.NOTIFICATION, Action.STOP, 123)
    match = re.match(views.CALLBACK_PATTERN, data)

    assert match is not None
    assert views.parse_callback(match.groups()) == ButtonPress(
        Source.NOTIFICATION, Action.STOP, 123
    )
    assert len(data.encode()) <= 64  # limite do Telegram


def test_tracked_text_without_target_explains_drop_rule() -> None:
    text = views.tracked_text(make_product())

    assert "✅ Monitorando: SSD 1TB" in text
    assert "💰 Preço atual: R$ 500,00" in text
    assert "Sem alvo" in text


def test_tracked_text_already_below_target() -> None:
    text = views.tracked_text(make_product(target_cents=60000, target_alerted=True))

    assert "🎯 Alvo: R$ 600,00" in text
    assert "Já está no alvo" in text


def test_tracked_text_out_of_stock() -> None:
    text = views.tracked_text(make_product(in_stock=False))

    assert "Sem estoque (último preço: R$ 500,00)" in text


def test_product_list_shows_price_lowest_and_target() -> None:
    products = [
        make_product(1, last_price_cents=55000, lowest_price_cents=50000, target_cents=45000),
        make_product(2, title="Mouse", last_price_cents=9990, lowest_price_cents=9990),
    ]

    text = views.product_list_text(products, MAX_PRODUCTS)

    assert text.startswith(f"📦 Produtos monitorados (2/{MAX_PRODUCTS}):")
    assert "1. SSD 1TB\n   R$ 550,00 · menor R$ 500,00 · alvo R$ 450,00" in text
    assert "2. Mouse\n   R$ 99,90" in text
    assert "menor R$ 99,90" not in text  # menor = atual: não repete


def test_full_product_list_fits_in_one_telegram_message() -> None:
    products = [
        make_product(
            i,
            title="X" * 300,
            last_price_cents=999_999_99,
            lowest_price_cents=1,
            target_cents=999_999_99,
            in_stock=False,
        )
        for i in range(1, MAX_PRODUCTS + 1)
    ]

    assert len(views.product_list_text(products, MAX_PRODUCTS)) <= 4096


def test_product_list_keyboard_groups_buttons_in_rows_of_five() -> None:
    products = [make_product(i) for i in range(1, 8)]

    keyboard = views.product_list_keyboard(products)

    assert keyboard is not None
    assert [len(row) for row in keyboard.inline_keyboard] == [5, 2]
    assert keyboard.inline_keyboard[1][1].callback_data == "prc:l:stop:7"


def test_empty_list_has_no_keyboard() -> None:
    assert "Nenhum produto" in views.product_list_text([], MAX_PRODUCTS)
    assert views.product_list_keyboard([]) is None


def test_alert_text_joins_several_kinds_in_one_message() -> None:
    product = make_product(target_cents=45000, last_price_cents=44000)
    alert = PriceAlert(product, (AlertKind.BACK_IN_STOCK, AlertKind.TARGET_REACHED), 50000)

    assert views.alert_text(alert).splitlines() == [
        "🛒 SSD 1TB",
        "📦 Voltou ao estoque por R$ 440,00",
        "🎯 Chegou no alvo de R$ 450,00! Agora: R$ 440,00",
        URL,
    ]


def test_alert_text_price_drop_shows_percent() -> None:
    alert = PriceAlert(make_product(last_price_cents=47500), (AlertKind.PRICE_DROP,), 50000)

    assert "📉 Caiu 5%: de R$ 500,00 para R$ 475,00" in views.alert_text(alert)


def test_alert_text_problems() -> None:
    failing = PriceAlert(make_product(), (AlertKind.READ_FAILING,), 50000)
    blocked = PriceAlert(make_product(), (AlertKind.STORE_BLOCKED,), 50000)

    assert "Não estou conseguindo ler o preço" in views.alert_text(failing)
    assert "A Kabum está recusando" in views.alert_text(blocked)


def test_alert_keyboard_has_stop_button() -> None:
    alert = PriceAlert(make_product(7), (AlertKind.PRICE_DROP,), 60000)

    [[button]] = views.alert_keyboard(alert).inline_keyboard

    assert button.callback_data == "prc:n:stop:7"


def test_stopped_text_keeps_alert_and_marks_it() -> None:
    assert views.stopped_text("🛒 SSD").endswith("🗑 Parei de monitorar este produto.")
