from collections.abc import Sequence

from telegram import CallbackQuery, Message, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from assistant.modules.prices import views
from assistant.modules.prices.money import MoneyParseError, parse_brl
from assistant.modules.prices.service import (
    MAX_PRODUCTS,
    PriceService,
    PriceValidationError,
    ProductNotFoundError,
)
from assistant.modules.prices.sources import (
    PriceFetchError,
    StoreBlockedError,
    UnsupportedStoreError,
)
from assistant.modules.prices.views import Source


def parse_track_args(args: Sequence[str]) -> tuple[str, int | None]:
    """['<link>', '1.149,90'] -> (link, 114990). O alvo é opcional e pode ter 'R$ ' na frente."""
    if not args:
        raise MoneyParseError("Faltou o link do produto.")
    url, *rest = args
    target = " ".join(rest)
    return url, parse_brl(target) if target else None


class PriceHandlers:
    """Adaptador entre o Telegram e o PriceService"""

    def __init__(self, service: PriceService, *, max_products: int = MAX_PRODUCTS) -> None:
        self._service = service
        self._max_products = max_products

    async def track(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, chat = update.effective_message, update.effective_chat
        if message is None or chat is None:
            return
        if not context.args:
            await message.reply_text(views.USAGE)
            return

        try:
            url, target_cents = parse_track_args(context.args)
        except MoneyParseError as exc:
            await message.reply_text(f"{exc}\n\n{views.USAGE}")
            return

        await context.bot.send_chat_action(chat.id, ChatAction.TYPING)
        try:
            product = await self._service.track(chat.id, url, target_cents)
        except UnsupportedStoreError:
            await message.reply_text(f"Essa loja ainda não é suportada.\n\n{views.USAGE}")
            return
        except PriceValidationError as exc:
            await message.reply_text(str(exc))
            return
        except StoreBlockedError:
            await message.reply_text("A loja recusou a consulta agora. Tente de novo mais tarde.")
            return
        except PriceFetchError as exc:
            await message.reply_text(f"Não consegui ler o preço dessa página. ({exc})")
            return

        await message.reply_text(views.tracked_text(product))

    async def list_products(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, chat = update.effective_message, update.effective_chat
        if message is None or chat is None:
            return
        products = await self._service.list_products(chat.id)
        await message.reply_text(
            views.product_list_text(products, self._max_products),
            reply_markup=views.product_list_keyboard(products),
        )

    async def on_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query, chat = update.callback_query, update.effective_chat
        if query is None or chat is None or context.match is None:
            return

        press = views.parse_callback(context.match.groups())
        try:
            await self._service.untrack(chat.id, press.product_id)
            feedback = "Parei de monitorar."
        except ProductNotFoundError:
            feedback = "Esse produto já não estava sendo monitorado."

        if press.source is Source.LIST:
            await self._refresh_list(query, chat.id)
        else:
            await self._mark_alert_stopped(query)
        await query.answer(feedback)

    async def _refresh_list(self, query: CallbackQuery, chat_id: int) -> None:
        products = await self._service.list_products(chat_id)
        try:
            await query.edit_message_text(
                views.product_list_text(products, self._max_products),
                reply_markup=views.product_list_keyboard(products),
            )
        except BadRequest as exc:
            # Dois cliques rápidos: a lista já está atualizada e o Telegram recusa editar igual.
            if "not modified" not in exc.message.lower():
                raise

    @staticmethod
    async def _mark_alert_stopped(query: CallbackQuery) -> None:
        message = query.message
        # Mensagens com mais de 48h viram "inacessíveis" (sem texto): aí só tira o botão.
        if isinstance(message, Message) and message.text:
            await query.edit_message_text(views.stopped_text(message.text), reply_markup=None)
        else:
            await query.edit_message_reply_markup(reply_markup=None)
