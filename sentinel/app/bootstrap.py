import asyncio
import logging
from pathlib import Path
from contextlib import suppress
from typing import cast

from telegram.ext import AIORateLimiter, ApplicationBuilder, ContextTypes
from web3 import AsyncWeb3, WebSocketProvider

from sentinel.app.application import SentinelApplication
from sentinel.app.context import BotContext
from sentinel.app.health import HealthServer, HealthState
from sentinel.app.module_adapter import build_module_adapter_from_config
from sentinel.app.runtime import BotRuntime
from sentinel.app.storage import create_persistence
from sentinel.app.telegram_adapters import (
    TelegramNotificationHandler,
    TelegramNotificationSink,
    TelegramProcessingStateProvider,
)
from sentinel.chain import ConnectOnDemand
from sentinel.config import get_config, get_healthcheck_bind_from_env
from sentinel.utils import normalize_block_number
from sentinel.handlers.errors import error_handler, build_error_callback
from sentinel.services.subscription import (
    ModuleRuntimeSupervisor,
)
from sentinel.jobs import JobContext

logger = logging.getLogger(__name__)


def create_runtime() -> BotRuntime:
    health = HealthState()
    health_host, health_port = get_healthcheck_bind_from_env()
    health_server = HealthServer(health, host=health_host, port=health_port)
    health_server.start()

    try:
        cfg = get_config()
        if cfg.token is None:
            raise RuntimeError("TOKEN must be configured")

        storage_path = Path(cfg.filestorage_path)
        storage_path.mkdir(parents=True, exist_ok=True)

        persistence = create_persistence(storage_path)

        context_types = ContextTypes(context=BotContext)

        application = cast(
            SentinelApplication,
            ApplicationBuilder()
            .application_class(SentinelApplication)
            .token(cfg.token)
            .context_types(context_types)
            .persistence(persistence)
            .rate_limiter(AIORateLimiter(max_retries=5))
            .build(),
        )

        persistent_provider = AsyncWeb3(
            WebSocketProvider(cfg.web3_socket_provider, max_connection_retries=-1)
        )
        rpc_provider = AsyncWeb3(
            WebSocketProvider(cfg.web3_socket_provider, max_connection_retries=-1)
        )
        backfill_provider = AsyncWeb3(
            WebSocketProvider(cfg.web3_socket_provider, max_connection_retries=-1)
        )

        chain = ConnectOnDemand(rpc_provider)
        module_adapter = build_module_adapter_from_config(cfg, rpc_provider, chain)

        module_supervisor = ModuleRuntimeSupervisor(
            persistent_provider,
            config=cfg,
            chain=chain,
            health=health,
            module_adapter=module_adapter,
            storage=TelegramProcessingStateProvider(application),
            notification_sink=TelegramNotificationSink(application),
            backfill_w3=backfill_provider,
        )
        notification_handler = TelegramNotificationHandler(
            application,
            lambda: module_supervisor.event_messages,
        )
        job_context = JobContext(module_supervisor)

        runtime = BotRuntime(
            application=application,
            module_supervisor=module_supervisor,
            notification_handler=notification_handler,
            job_context=job_context,
            chain=chain,
            health=health,
            health_server=health_server,
        )
        application.attach_runtime(runtime)
        return runtime
    except Exception as exc:
        health.mark_fatal_error(exc)
        health_server.stop()
        raise


async def _run(runtime: BotRuntime) -> None:
    application = runtime.application
    module_supervisor = runtime.module_supervisor
    job_context = runtime.job_context
    cfg = runtime.config

    updater = application.updater
    if updater is None:
        raise RuntimeError("Application updater is not configured; cannot start polling")

    await application.initialize()
    await application.start()
    application.add_error_handler(error_handler)

    heartbeat_task = asyncio.create_task(runtime.health.heartbeat_loop())
    module_supervisor_task: asyncio.Task[None] | None = None
    try:
        module_supervisor.ensure_state_containers()
        runtime.health.mark_warmup_started()
        try:
            await runtime.module_adapter.warm_up()
        except Exception as exc:
            runtime.health.mark_warmup_failed(exc)
            logger.warning("Failed to warm up module adapter cache", exc_info=True)
        else:
            runtime.health.mark_warmup_complete()

        application.bot_data["admin_ids"] = cfg.admin_ids

        persisted_block = normalize_block_number(application.bot_data.get("block"))
        block_from = (
            cfg.block_from
            if cfg.block_from is not None
            else (persisted_block + 1 if persisted_block is not None else None)
        )

        logger.info(
            "Bot started. Backfill start block: %s",
            block_from,
        )

        error_callback = build_error_callback(application)
        await updater.start_polling(error_callback=error_callback)
        runtime.health.mark_polling_started()
        module_supervisor.setup_signal_handlers(asyncio.get_running_loop())

        # Start the live subscription first, then backfill up to a post-subscribe head.
        # This avoids missing blocks mined while historical catch-up is running.
        module_supervisor_task = asyncio.create_task(module_supervisor.subscribe())
        await module_supervisor.wait_until_subscribed()
        runtime.health.mark_startup_complete()

        if block_from:
            await module_supervisor.catch_up_from(block_from)

        await job_context.schedule(application)

        await module_supervisor_task
    except asyncio.CancelledError:  # pragma: no cover - shutdown guard
        pass
    except Exception as exc:
        runtime.health.mark_fatal_error(exc)
        raise
    finally:
        runtime.health.mark_shutdown_requested()
        # Ensure shutdown never hangs on unexpected failures (e.g., subscription startup timeouts).
        module_supervisor.request_shutdown()
        if module_supervisor_task is not None and not module_supervisor_task.done():
            module_supervisor_task.cancel()
            with suppress(asyncio.CancelledError):
                await module_supervisor_task
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        await module_supervisor.close()
        await updater.stop()
        await application.stop()
        await application.shutdown()
        runtime.health_server.stop()


def run(runtime: BotRuntime) -> None:
    asyncio.run(_run(runtime))
