from telegram.ext import CallbackQueryHandler, CommandHandler

from assistant.config import Settings
from assistant.main import build_application, build_context
from assistant.modules.prices.jobs import CHECK_JOB_ID
from assistant.modules.reminders.jobs import DISPATCH_JOB_ID


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        telegram_bot_token="123:fake",
        allowed_chat_id=1,
        database_url="sqlite+aiosqlite:///:memory:",
    )


async def test_application_wires_commands_and_jobs() -> None:
    ctx = build_context(make_settings())

    app = build_application(ctx)

    commands = {
        command
        for handler in app.handlers[0]
        if isinstance(handler, CommandHandler)
        for command in handler.commands
    }
    assert {"start", "lembrete", "lembretes", "concluidos", "monitorar", "produtos"} <= commands
    assert sum(isinstance(h, CallbackQueryHandler) for h in app.handlers[0]) == 2
    assert ctx.scheduler.get_job(DISPATCH_JOB_ID) is not None
    assert ctx.scheduler.get_job(CHECK_JOB_ID) is not None

    await ctx.shutdown(app)  # fecha o cliente HTTP do monitor de preços


async def test_shutdown_works_even_if_startup_never_ran() -> None:
    # Ex.: token inválido derruba a subida antes do post_init, mas o post_shutdown roda mesmo assim.
    ctx = build_context(make_settings())
    app = build_application(ctx)

    await ctx.shutdown(app)

    assert not ctx.scheduler.running


async def test_shutdown_runs_cleanups_in_reverse_order_even_if_one_fails() -> None:
    ctx = build_context(make_settings())
    app = build_application(ctx)
    calls: list[str] = []

    async def first() -> None:
        calls.append("first")

    async def broken() -> None:
        raise RuntimeError("falhou ao fechar")

    async def last() -> None:
        calls.append("last")

    ctx.on_shutdown(first)
    ctx.on_shutdown(broken)
    ctx.on_shutdown(last)

    await ctx.shutdown(app)

    assert calls == ["last", "first"]
