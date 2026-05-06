"""Runtime orchestration: Bootstrap, Runtime, EODManager.

Split out of the original monolithic main.py for testability — each piece
takes a ``BotContext`` and can be exercised in isolation.
"""

from src.runtime.context import BotContext
from src.runtime.bootstrap import Bootstrap
from src.runtime.runtime import Runtime
from src.runtime.eod import EODManager

__all__ = ["BotContext", "Bootstrap", "Runtime", "EODManager"]
