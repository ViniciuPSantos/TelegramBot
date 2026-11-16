"""Importa todos os models para registrá-los em Base.metadata (usado pelo Alembic).

Ao criar um módulo novo com tabelas, adicione o import dele aqui.
"""

from assistant.modules.prices.models import PricePoint, TrackedProduct
from assistant.modules.reminders.models import Reminder

__all__ = ["PricePoint", "Reminder", "TrackedProduct"]
