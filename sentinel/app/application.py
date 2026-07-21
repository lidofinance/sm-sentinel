from typing import Any, TYPE_CHECKING

from telegram.ext import Application

if TYPE_CHECKING:
    from sentinel.app.runtime import BotRuntime


class SentinelApplication(Application):
    """PTB application with an explicitly attached bot runtime."""

    __slots__ = ("_runtime",)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._runtime: BotRuntime | None = None

    def attach_runtime(self, runtime: "BotRuntime") -> None:
        self._runtime = runtime

    @property
    def runtime(self) -> "BotRuntime":
        if self._runtime is None:
            raise RuntimeError("Bot runtime is not attached to the application")
        return self._runtime
