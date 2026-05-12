from dataclasses import dataclass
from typing import TYPE_CHECKING

from sentinel.config import Config

if TYPE_CHECKING:
    from telegram.ext import Application

    from sentinel.app.health import HealthServer, HealthState
    from sentinel.chain import ConnectOnDemand
    from sentinel.jobs import JobContext
    from sentinel.notifications import EventMessageEngine
    from sentinel.modules.base import ModuleAdapter
    from sentinel.services.subscription import TelegramSubscription


_RUNTIME_ATTR = "_module_runtime"


@dataclass(slots=True)
class BotRuntime:
    """Lightweight container for the long-lived bot context."""

    config: Config
    application: "Application"
    subscription: "TelegramSubscription"
    event_messages: "EventMessageEngine"
    job_context: "JobContext"
    module_adapter: "ModuleAdapter"
    chain: "ConnectOnDemand"
    health: "HealthState"
    health_server: "HealthServer"


def attach_runtime(runtime: BotRuntime) -> None:
    """Attach the runtime to the Application instance for easy lookup."""
    setattr(runtime.application, _RUNTIME_ATTR, runtime)


def get_runtime_from_application(application: "Application") -> BotRuntime:
    runtime = getattr(application, _RUNTIME_ATTR, None)
    if runtime is None:
        raise RuntimeError("Bot runtime is not attached to the application")
    return runtime
