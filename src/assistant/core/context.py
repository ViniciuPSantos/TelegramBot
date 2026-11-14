import logging
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from telegram.ext import Application

from assistant.config import Settings
from assistant.core.handlers import BOT_COMMANDS

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AppContext:
    """Dependencias compartilhadas que os modulos recebem ao se registrar"""

    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    scheduler: AsyncIOScheduler

    async def startup(self, app: Application) -> None:
        await app.bot.set_my_commands(BOT_COMMANDS)
        self.scheduler.start()
        logger.info("scheduler iniciado")

    async def shutdown(self, app: Application) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await self.engine.dispose()
        logger.info("recursos liberados")
