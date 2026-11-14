from telegram.ext import CallbackQueryHandler, CommandHandler

from assistant.config import Settings
from assistant.main import build_application, build_context
from assistant.modules.reminders.jobs import DISPATCH_JOB_ID


def test_application_wires_commands_and_jobs() -> None:
    # _env_file=None: o teste não depende do .env da máquina.
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        telegram_bot_token="123:fake",
        allowed_chat_id=1,
        database_url="sqlite+aiosqlite:///:memory:",
    )
    ctx = build_context(settings)

    app = build_application(ctx)

    commands = {
        command
        for handler in app.handlers[0]
        if isinstance(handler, CommandHandler)
        for command in handler.commands
    }
    assert {"start", "lembrete", "lembretes", "concluidos"} <= commands
    assert any(isinstance(h, CallbackQueryHandler) for h in app.handlers[0])
    assert ctx.scheduler.get_job(DISPATCH_JOB_ID) is not None
