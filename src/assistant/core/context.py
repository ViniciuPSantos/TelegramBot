import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from telegram.ext import Application

from assistant.config import Settings
from assistant.core.handlers import BOT_COMMANDS

logger = logging.getLogger(__name__)

Cleanup = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AppContext:
    """Dependencias compartilhadas que os modulos recebem ao se registrar"""

    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    scheduler: AsyncIOScheduler
    _cleanups: list[Cleanup] = field(default_factory=list, init=False, repr=False)

    def on_shutdown(self, cleanup: Cleanup) -> None:
        self._cleanups.append(cleanup)

    async def startup(self, app: Application) -> None:
        await app.bot.set_my_commands(BOT_COMMANDS)
        self.scheduler.start()
        logger.info("scheduler iniciado")

    async def shutdown(self, app: Application) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        # Ordem inversa do registro, como um try-with-resources com vários recursos.
        for cleanup in reversed(self._cleanups):
            try:
                await cleanup()
            except Exception:
                logger.exception("falha ao liberar recurso de módulo")
        await self.engine.dispose()
        logger.info("recursos liberados")
